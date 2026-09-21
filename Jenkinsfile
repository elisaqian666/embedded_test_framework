pipeline {
    agent { label 'docker' }

    options {
        timestamps()
        disableConcurrentBuilds(abortPrevious: true)
        buildDiscarder(logRotator(numToKeepStr: '30', artifactDaysToKeepStr: '1'))
    }

    environment {
        ARTIFACTORY_REGISTRY = 'jfrog.local'
        ARTIFACTORY_DOCKER_REPO = 'embedded-test-local'
        IMAGE = "${ARTIFACTORY_REGISTRY}/${ARTIFACTORY_DOCKER_REPO}/embedded-framework"
        ARTIFACTORY_CREDENTIALS = credentials('jfrog-credentials')
        ARTIFACTORY_TEST_RESULTS_REPO = 'test-results-local'
    }

    stages {
        stage('Unittests') {
            options { timeout(time: 1, unit: 'HOURS') }
            steps {
                sh 'rm -rf test-results && mkdir -p test-results'
                sh 'docker build -t embedded-framework-test:${BUILD_NUMBER} .'
                sh 'docker run --rm -v "$WORKSPACE/test-results:/test-results" embedded-framework-test:${BUILD_NUMBER} python -m pytest -q /app/embedded_framework/tests --junitxml=/test-results/junit-${BUILD_NUMBER}.xml'
            }
        }
        stage('Publish image') {
            when { branch 'master' }
            steps {
                sh 'docker tag embedded-framework-test:${BUILD_NUMBER} ${IMAGE}:${BUILD_NUMBER}'
                sh 'echo "$ARTIFACTORY_CREDENTIALS_PSW" | docker login "$ARTIFACTORY_REGISTRY" --username "$ARTIFACTORY_CREDENTIALS_USR" --password-stdin'
                sh 'docker push ${IMAGE}:${BUILD_NUMBER}'
            }
        }
    }
    post {
        always {
            junit allowEmptyResults: true, keepProperties: true, testResults: 'test-results/junit-*.xml'
            archiveArtifacts allowEmptyArchive: true, artifacts: 'test-results/junit-*.xml'
            sh '''
                TEST_REPORT="junit-${BUILD_NUMBER}.xml"
                TEST_PATH="$(date +%Y-%m-%d)/build-${BUILD_NUMBER}"
                if test -f "test-results/${TEST_REPORT}"; then
                    curl -f \
                        -u "$ARTIFACTORY_CREDENTIALS_USR:$ARTIFACTORY_CREDENTIALS_PSW" \
                        -T "test-results/${TEST_REPORT}" \
                        "https://${ARTIFACTORY_REGISTRY}/artifactory/${ARTIFACTORY_TEST_RESULTS_REPO}/${TEST_PATH}/${TEST_REPORT}"
                fi
            '''
            sh 'docker rmi -f embedded-framework-test:${BUILD_NUMBER} || true'
            sh 'docker logout ${ARTIFACTORY_REGISTRY} || true'
        }
    }
}
