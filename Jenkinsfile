pipeline {
    agent { label 'docker' }

    environment {
        ARTIFACTORY_REGISTRY = '192.168.1.104:8081'
        ARTIFACTORY_DOCKER_REPO = 'embedded-test-local'
        IMAGE = "${ARTIFACTORY_REGISTRY}/${ARTIFACTORY_DOCKER_REPO}/embedded-framework"
    }

    stages {
        stage('Unit tests') {
            steps {
                sh 'docker build -t embedded-framework-test:${BUILD_NUMBER} .'
                sh 'docker run --rm embedded-framework-test:${BUILD_NUMBER}'
            }
        }
        stage('Publish image') {
            when { branch 'main' }
            steps {
                sh 'docker tag embedded-framework-test:${BUILD_NUMBER} ${IMAGE}:${BUILD_NUMBER}'
                withCredentials([usernamePassword(credentialsId: 'artifactory-docker', usernameVariable: 'ARTIFACTORY_USER', passwordVariable: 'ARTIFACTORY_TOKEN')]) {
                    sh 'echo "$ARTIFACTORY_TOKEN" | docker login "$ARTIFACTORY_REGISTRY" --username "$ARTIFACTORY_USER" --password-stdin'
                    sh 'docker push ${IMAGE}:${BUILD_NUMBER}'
                }
            }
        }
    }
    post {
        always { sh 'docker logout ${ARTIFACTORY_REGISTRY} || true' }
    }
}
