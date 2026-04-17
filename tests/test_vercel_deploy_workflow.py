from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class VercelDeployWorkflowTests(unittest.TestCase):
    def test_vercel_workflow_uses_remote_prod_deploy_instead_of_prebuilt_artifacts(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "vercel-deploy.yml").read_text(encoding="utf-8")

        self.assertIn("vercel deploy --prod --yes", workflow)
        self.assertNotIn("vercel build --prod", workflow)
        self.assertNotIn("--prebuilt", workflow)


if __name__ == "__main__":
    unittest.main()