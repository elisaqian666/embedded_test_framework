// Agent needs Python 3.11+ (python3 on Unix, python on Windows).
pipeline {
    agent any
    options {
        skipDefaultCheckout(true)
        disableConcurrentBuilds()
        timeout(time: 20, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '20'))
    }
    environment {
        PYTHONDONTWRITEBYTECODE = '1'
        PIP_DISABLE_PIP_VERSION_CHECK = '1'
    }
    stages {
        stage('Checkout') {
            steps {
                deleteDir()
                checkout scm
            }
        }
        stage('Install') {
            steps {
                script {
                    if (isUnix()) {
                        sh 'python3 -m venv .venv'
                        sh '.venv/bin/python -m pip install ".[test]"'
                    } else {
                        bat 'python -m venv .venv'
                        bat '.venv\\Scripts\\python.exe -m pip install ".[test]"'
                    }
                }
            }
        }
        stage('Unit tests') {
            steps {
                script {
                    if (isUnix()) {
                        sh '.venv/bin/python -m pytest unittest --junitxml=reports/unit.xml'
                    } else {
                        bat '.venv\\Scripts\\python.exe -m pytest unittest --junitxml=reports/unit.xml'
                    }
                }
            }
            post { always { junit testResults: 'reports/unit.xml', allowEmptyResults: false } }
        }
        stage('Consumer examples') {
            steps {
                script {
                    if (isUnix()) {
                        sh '.venv/bin/python -m pytest examples/external_tests --device-config examples/external_tests/devices.json --junitxml=reports/examples.xml'
                    } else {
                        bat '.venv\\Scripts\\python.exe -m pytest examples/external_tests --device-config examples/external_tests/devices.json --junitxml=reports/examples.xml'
                    }
                }
            }
            post { always { junit testResults: 'reports/examples.xml', allowEmptyResults: false } }
        }
        stage('Build wheel') {
            steps {
                script {
                    if (isUnix()) {
                        sh '.venv/bin/python -m pip wheel . --no-deps -w dist'
                    } else {
                        bat '.venv\\Scripts\\python.exe -m pip wheel . --no-deps -w dist'
                    }
                }
                archiveArtifacts artifacts: 'dist/*.whl', fingerprint: true
            }
        }
    }
}
