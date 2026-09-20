"""Common Jenkins operations used by automated tests."""

import os
from typing import Any

import jenkins

from embedded_framework.lib.custom_exception import EmbeddedFrameworkException


class JenkinsHelperError(EmbeddedFrameworkException):
    """Base exception for Jenkins helper failures."""


class JenkinsHelper:
    """Small wrapper around python-jenkins for job, build and node operations."""

    def __init__(
        self,
        url: str,
        username: str,
        token: str,
    ) -> None:
        if not url:
            raise ValueError("Jenkins URL must not be empty")
        if not username:
            raise ValueError("Jenkins username must not be empty")
        if not token:
            raise ValueError("Jenkins token must not be empty")

        self.server = jenkins.Jenkins(
            url.rstrip("/"),
            username=username,
            password=token,
        )

    def get_version(self) -> str:
        """Return Jenkins server version."""
        return self.server.get_version()

    def start_build(
        self,
        job_name: str,
        parameters: dict[str, Any] | None = None,
    ) -> int:
        """Queue a Jenkins job and return its queue item id."""
        return self.server.build_job(
            job_name,
            parameters=parameters or {},
        )

    def stop_build(
        self,
        job_name: str,
        build_number: int,
    ) -> None:
        """Stop a running build."""
        self.server.stop_build(
            job_name,
            build_number,
        )

    def get_job_info(self, job_name: str) -> dict[str, Any]:
        """Return Jenkins job information."""
        return self.server.get_job_info(job_name)

    def get_build_info(
        self,
        job_name: str,
        build_number: int,
    ) -> dict[str, Any]:
        """Return Jenkins build information."""
        return self.server.get_build_info(
            job_name,
            build_number,
        )

    def get_last_build_number(self, job_name: str) -> int | None:
        """Return the latest build number, or None if the job has never run."""
        last_build = self.get_job_info(job_name).get("lastBuild")
        return last_build["number"] if last_build else None

    def get_last_successful_build_number(
        self,
        job_name: str,
    ) -> int | None:
        """Return the last successful build number."""
        build = self.get_job_info(job_name).get(
            "lastSuccessfulBuild"
        )
        return build["number"] if build else None

    def is_build_running(
        self,
        job_name: str,
        build_number: int,
    ) -> bool:
        """Return whether a build is currently running."""
        return bool(
            self.get_build_info(
                job_name,
                build_number,
            ).get("building")
        )

    def get_build_result(
        self,
        job_name: str,
        build_number: int,
    ) -> str | None:
        """Return build result such as SUCCESS, FAILURE or ABORTED.

        None usually means the build is still running.
        """
        return self.get_build_info(
            job_name,
            build_number,
        ).get("result")

    def get_queue(self) -> list[dict[str, Any]]:
        """Return current Jenkins queue."""
        return self.server.get_queue_info()

    def cancel_queue(self, queue_id: int) -> None:
        """Cancel a queued Jenkins item."""
        self.server.cancel_queue(queue_id)

    def get_nodes(self) -> list[dict[str, Any]]:
        """Return Jenkins nodes."""
        return self.server.get_nodes()

    def get_node_info(self, node_name: str) -> dict[str, Any]:
        """Return information for one Jenkins node."""
        return self.server.get_node_info(node_name)

    def is_node_online(self, node_name: str) -> bool:
        """Return whether a Jenkins node is online."""
        return not self.get_node_info(node_name).get(
            "offline",
            True,
        )

    def get_node_labels(self, node_name: str) -> list[str]:
        """Return labels assigned to a Jenkins node."""
        node = self.get_node_info(node_name)

        return [
            label["name"]
            for label in node.get("assignedLabels", [])
            if label.get("name")
        ]

    @staticmethod
    def current_job_name() -> str | None:
        """Return current Jenkins job name when running under Jenkins."""
        return os.getenv("JOB_NAME")

    @staticmethod
    def current_build_number() -> int | None:
        """Return current Jenkins build number."""
        value = os.getenv("BUILD_NUMBER")
        return int(value) if value and value.isdigit() else None

    @staticmethod
    def current_build_url() -> str | None:
        """Return current Jenkins build URL."""
        return os.getenv("BUILD_URL")

    @staticmethod
    def current_node_name() -> str | None:
        """Return current Jenkins node name."""
        return os.getenv("NODE_NAME")

    @staticmethod
    def current_node_labels() -> list[str]:
        """Return labels of the current Jenkins node."""
        return os.getenv("NODE_LABELS", "").split()


if __name__ == "__main__":
    # Small self-check that does not require a Jenkins server.
    assert JenkinsHelper.current_node_labels() == os.getenv(
        "NODE_LABELS",
        "",
    ).split()

    print("self-check passed")