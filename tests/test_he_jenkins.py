from unittest.mock import Mock, patch

from embedded_framework.helpers.he_jenkins import JenkinsHelper


@patch("embedded_framework.helpers.he_jenkins.jenkins.Jenkins")
def test_start_build_passes_parameters_to_jenkins(jenkins_client: Mock) -> None:
    server = jenkins_client.return_value
    server.build_job.return_value = 42
    helper = JenkinsHelper("http://192.168.1.104:8080", "ci-user", "token")

    assert helper.start_build("embedded-framework", {"branch": "main"}) == 42
    jenkins_client.assert_called_once_with("http://192.168.1.104:8080", username="ci-user", password="token")
    server.build_job.assert_called_once_with("embedded-framework", parameters={"branch": "main"})
