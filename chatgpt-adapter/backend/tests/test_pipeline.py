from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(BACKEND))

from ars_mcp import pipeline  # noqa: E402


class PipelineStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"ARS_STATE_DB": str(Path(self.tmp.name) / "state.sqlite3")})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(self.tmp.cleanup)

    def create(self, workflow_type="full", starting_stage=None):
        result = pipeline.create_project(
            "A test project",
            workflow_type=workflow_type,
            research_question="How does the intervention affect outcome X?",
            starting_stage=starting_stage,
        )
        self.project_id = result["project"]["project_id"]
        self.token = result["access_token"]
        return result["project"]

    def finish(self, stage, outcome="complete", summary="Stage checked"):
        return pipeline.finish_stage(self.project_id, self.token, stage, outcome, summary)

    def decide(self, choice):
        return pipeline.decide(self.project_id, self.token, choice, "Test rationale")

    def test_create_persists_metadata_and_returns_one_time_token(self):
        project = self.create()
        self.assertEqual(project["current_stage"], "research")
        self.assertEqual(project["status"], "active")
        self.assertEqual(project["state"]["stage_states"]["research"]["attempts"], 1)
        fetched = pipeline.get_project(self.project_id, self.token)
        self.assertEqual(fetched["title"], "A test project")
        self.assertNotIn("access_token", fetched)
        self.assertFalse(fetched["state"]["privacy"]["document_contents_persisted"])

    def test_database_file_is_private_on_posix(self):
        self.create()
        if os.name != "nt":
            import stat
            database = Path(os.environ["ARS_STATE_DB"])
            mode = stat.S_IMODE(database.stat().st_mode)
            self.assertEqual(mode & 0o077, 0)

    def test_invalid_token_does_not_disclose_project(self):
        self.create()
        with self.assertRaises(PermissionError):
            pipeline.get_project(self.project_id, "x" * 48)
        with self.assertRaises(PermissionError):
            pipeline.get_project("not-a-project", self.token)

    def test_full_pipeline_transitions_and_user_checkpoints(self):
        self.create()
        self.finish("research")
        self.assertEqual(self.decide("continue")["current_stage"], "write")
        self.finish("write")
        self.assertEqual(self.decide("continue")["current_stage"], "pre_review_integrity")
        self.finish("pre_review_integrity", "pass")
        self.assertEqual(self.decide("continue")["current_stage"], "peer_review")
        self.finish("peer_review", "minor_revision")
        self.assertEqual(self.decide("revise")["current_stage"], "revise")
        self.finish("revise")
        self.assertEqual(self.decide("continue")["current_stage"], "re_review")
        self.finish("re_review", "major_revision")
        self.assertEqual(self.decide("revise")["current_stage"], "re_revise")
        self.finish("re_revise")
        self.assertEqual(self.decide("continue")["current_stage"], "final_integrity")
        self.finish("final_integrity", "pass")
        self.assertEqual(self.decide("continue")["current_stage"], "finalize")
        self.finish("finalize")
        self.assertEqual(self.decide("continue")["current_stage"], "process_summary")
        self.finish("process_summary")
        final = self.decide("finish")
        self.assertEqual(final["status"], "completed")
        self.assertEqual(final["state"]["closed_reason"], "process_summary_completed")
        self.assertEqual(final["state"]["current_stage_status"], "completed")
        self.assertGreaterEqual(len(final["history"]), 20)

    def test_integrity_fail_requires_revise_and_only_allows_risk_bypass_after_three_rounds(self):
        self.create(starting_stage="pre_review_integrity")
        self.finish("pre_review_integrity", "fail", "Integrity failure")
        with self.assertRaises(ValueError):
            self.decide("continue")
        self.assertEqual(self.decide("revise")["current_stage"], "write")
        for round_index in range(2):
            self.finish("write")
            self.decide("continue")
            third = self.finish("pre_review_integrity", "fail", "Further integrity failure")
            if round_index == 0:
                self.decide("revise")
        self.assertEqual(third["state"]["integrity_failure_rounds"]["pre_review"], 3)
        with self.assertRaises(ValueError):
            self.decide("continue")
        bypassed = self.decide("bypass_with_risk")
        self.assertEqual(bypassed["current_stage"], "peer_review")
        self.assertTrue(bypassed["state"]["stage_states"]["pre_review_integrity"]["risk_accepted"])
        self.assertEqual(bypassed["state"]["stage_states"]["pre_review_integrity"]["status"], "waived_with_risk")

    def test_pause_and_resume_preserve_pending_decision(self):
        self.create()
        self.finish("research")
        paused = pipeline.pause_project(self.project_id, self.token, "Need supervisor approval")
        self.assertEqual(paused["status"], "paused")
        resumed = pipeline.resume_project(self.project_id, self.token)
        self.assertEqual(resumed["status"], "active")
        self.assertTrue(resumed["state"]["decision_required"])
        self.assertEqual(resumed["state"]["current_stage_status"], "awaiting_decision")
        self.assertEqual(self.decide("continue")["current_stage"], "write")

    def test_artifact_registry_stores_hash_metadata_only(self):
        self.create()
        content = b"paper draft placeholder"
        digest = hashlib.sha256(content).hexdigest()
        artifact = pipeline.add_artifact(
            self.project_id, self.token, "research", "protocol.md", "protocol", digest,
            len(content), "drive://private/protocol", "Protocol accepted by researcher",
        )
        fetched = pipeline.get_project(self.project_id, self.token)
        self.assertEqual(fetched["artifacts"][0]["artifact_id"], artifact["artifact_id"])
        self.assertNotIn("content", fetched["artifacts"][0])
        self.assertEqual(fetched["artifacts"][0]["sha256"], digest)
        self.assertEqual(artifact["hash_validation"], "format_only; digest was not recomputed against file bytes")

    def test_artifact_only_allowed_for_current_active_stage(self):
        self.create()
        with self.assertRaises(ValueError):
            pipeline.add_artifact(self.project_id, self.token, "write", "draft.md", "manuscript", "a" * 64, 1)
        with self.assertRaises(ValueError):
            pipeline.add_artifact(self.project_id, self.token, "research", "../draft.md", "manuscript", "a" * 64, 1)
        with self.assertRaises(ValueError):
            pipeline.add_artifact(self.project_id, self.token, "research", "draft.md", "manuscript", "not-a-hash", 1)

    def test_review_outcome_must_match_user_decision(self):
        self.create(starting_stage="peer_review")
        self.finish("peer_review", "major_revision")
        with self.assertRaises(ValueError):
            self.decide("accept")
        self.assertEqual(self.decide("revise")["current_stage"], "revise")

    def test_reject_can_close_or_restart_but_never_silently_continue(self):
        self.create(starting_stage="peer_review")
        self.finish("peer_review", "reject")
        with self.assertRaises(ValueError):
            self.decide("continue")
        closed = self.decide("end")
        self.assertEqual(closed["status"], "closed")

    def test_finalize_can_skip_process_summary_only_by_explicit_decision(self):
        self.create(starting_stage="finalize")
        self.finish("finalize")
        final = self.decide("skip_summary")
        self.assertEqual(final["status"], "completed")
        self.assertEqual(final["state"]["closed_reason"], "process_summary_skipped_by_user")
        self.assertEqual(final["state"]["current_stage_status"], "completed")


    def test_pipeline_status_exposes_stage_contracts(self):
        status = pipeline.pipeline_status()
        self.assertEqual(len(status["stages"]), 10)
        self.assertIn("bypass_with_risk", status["stage_contracts"]["final_integrity"]["decisions"]["fail_after_three_rounds"])
        self.assertIn("skip_summary", status["stage_contracts"]["finalize"]["decisions"]["complete"])

    def test_start_mode_mapping_and_invalid_inputs(self):
        project = pipeline.create_project("Review this", workflow_type="existing_paper")
        self.assertEqual(project["project"]["current_stage"], "pre_review_integrity")
        with self.assertRaises(ValueError):
            pipeline.create_project("Bad workflow", workflow_type="anything")
        with self.assertRaises(ValueError):
            pipeline.create_project("Bad stage", starting_stage="shell")



    def test_reentering_a_stage_clears_old_result_but_preserves_attempt_counter(self):
        self.create()
        self.finish("research", summary="First research pass")
        self.decide("continue")
        self.finish("write")
        self.decide("continue")
        self.finish("pre_review_integrity", "fail", "A reported issue")
        self.decide("revise")
        self.finish("write", summary="Updated draft")
        self.decide("continue")
        state = pipeline.get_project(self.project_id, self.token)["state"]
        self.assertEqual(state["stage_states"]["pre_review_integrity"]["status"], "in_progress")
        self.assertIsNone(state["stage_states"]["pre_review_integrity"]["outcome"])
        self.assertNotIn("flagged_issues", state["stage_states"]["pre_review_integrity"])
        self.assertEqual(state["stage_states"]["pre_review_integrity"]["attempts"], 2)
        self.assertEqual(state["stage_states"]["pre_review_integrity"]["status"], "in_progress")

    def test_delete_requires_exact_confirmation_and_removes_project_data(self):
        self.create()
        with self.assertRaises(ValueError):
            pipeline.delete_project(self.project_id, self.token, "DELETE")
        deleted = pipeline.delete_project(self.project_id, self.token, f"DELETE {self.project_id}")
        self.assertTrue(deleted["deleted"])
        with self.assertRaises(PermissionError):
            pipeline.get_project(self.project_id, self.token)

    def test_event_ledger_is_durable_across_module_reopen(self):
        self.create()
        self.finish("research")
        before = len(pipeline.get_project(self.project_id, self.token)["history"])
        after = pipeline.get_project(self.project_id, self.token)
        self.assertEqual(len(after["history"]), before)
        self.assertEqual(after["history"][-1]["event_type"], "stage_finished")

    def test_concurrent_artifact_registration_is_transactionally_consistent(self):
        self.create()
        def add_one(index):
            payload = f"artifact-{index}".encode("utf-8")
            return pipeline.add_artifact(
                self.project_id, self.token, "research", f"artifact-{index}.txt", "other",
                hashlib.sha256(payload).hexdigest(), len(payload), "", "concurrency smoke fixture",
            )
        with ThreadPoolExecutor(max_workers=10) as executor:
            created = list(executor.map(add_one, range(24)))
        fetched = pipeline.get_project(self.project_id, self.token)
        self.assertEqual(len(created), 24)
        self.assertEqual(len(fetched["artifacts"]), 24)
        self.assertEqual(
            sum(event["event_type"] == "artifact_registered" for event in fetched["history"]),
            24,
        )


if __name__ == "__main__":
    unittest.main()
