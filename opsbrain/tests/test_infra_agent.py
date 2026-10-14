"""Unit tests for the infra agent's AWS tools, using moto to mock AWS (no real account/cost)."""

from __future__ import annotations

import unittest

import boto3
from infra.agent import InfraAgent, InfraConfig
from moto import mock_aws


class InfraAgentAwsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mock_aws = mock_aws()
        self.mock_aws.start()
        # Point at a missing kubeconfig so a developer's real ~/.kube/config
        # can't make the Kubernetes checks succeed.
        self.agent = InfraAgent(InfraConfig(aws_region="us-east-1", kubeconfig_path="/nonexistent/kubeconfig"))

    def tearDown(self) -> None:
        self.mock_aws.stop()

    def test_summarize_ec2_groups_instances_by_state(self) -> None:
        ec2 = boto3.client("ec2", region_name="us-east-1")
        ec2.run_instances(ImageId="ami-12345678", MinCount=2, MaxCount=2)

        summary = self.agent.summarize_ec2()

        self.assertEqual(summary["region"], "us-east-1")
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["state_breakdown"], {"running": 2})

    def test_list_eks_clusters_reports_status(self) -> None:
        eks = boto3.client("eks", region_name="us-east-1")
        eks.create_cluster(
            name="test-cluster",
            roleArn="arn:aws:iam::123456789012:role/test",
            resourcesVpcConfig={"subnetIds": ["subnet-123"]},
        )

        data = self.agent.list_eks_clusters()

        self.assertEqual(data["count"], 1)
        self.assertEqual(data["clusters"], [{"name": "test-cluster", "status": "ACTIVE"}])

    def test_list_rds_instances_reports_status_breakdown(self) -> None:
        rds = boto3.client("rds", region_name="us-east-1")
        rds.create_db_instance(
            DBInstanceIdentifier="test-db",
            DBInstanceClass="db.t3.micro",
            Engine="postgres",
            MasterUsername="admin",
            MasterUserPassword="password123",
            AllocatedStorage=20,
        )

        data = self.agent.list_rds_instances()

        self.assertEqual(data["count"], 1)
        self.assertEqual(data["status_breakdown"], {"available": 1})
        self.assertEqual(data["instances"][0]["identifier"], "test-db")

    def test_get_health_summary_reports_each_check_independently(self) -> None:
        ec2 = boto3.client("ec2", region_name="us-east-1")
        ec2.run_instances(ImageId="ami-12345678", MinCount=1, MaxCount=1)

        summary = self.agent.get_health_summary()

        # AWS checks succeed under moto; k8s checks fail (no kubeconfig) without
        # taking down the whole summary.
        self.assertTrue(summary["checks"]["ec2"]["ok"])
        self.assertTrue(summary["checks"]["eks"]["ok"])
        self.assertTrue(summary["checks"]["rds"]["ok"])
        self.assertFalse(summary["checks"]["nodes"]["ok"])
        self.assertEqual(summary["overall"], "degraded")


class InfraHealthFormatTests(unittest.TestCase):
    def test_health_answer_includes_passing_checks_alongside_failures(self) -> None:
        data = {
            "overall": "degraded",
            "checks": {
                "ec2": {"ok": False, "error": "Infra backend check failed (HTTP 500)."},
                "nodes": {"ok": True, "data": {"total_nodes": 1, "nodes": [{"ready": True}]}},
                "pods": {"ok": True, "data": {"total_pods": 3, "status_breakdown": {"healthy": 3}}},
            },
        }

        answer = InfraAgent._format_health_summary(data)

        self.assertEqual(
            answer,
            "Infra health: degraded — failed checks: ec2. nodes: 1/1 node(s) ready. pods: 3 pod(s) — healthy: 3.",
        )


if __name__ == "__main__":
    unittest.main()
