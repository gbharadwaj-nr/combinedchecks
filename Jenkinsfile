pipeline {
    agent any

    options {
        timestamps()
        timeout(time: 30, unit: 'MINUTES')
    }

    // Scheduled for twice-daily execution; adjust cron as required per environment.
    triggers {
        cron('0 6,18 * * *')
    }

    parameters {
        string(name: 'CLIENT_NAME', defaultValue: 'fleetcor', description: 'Client to run the Daily Health Check for')
    }

    environment {
        PYTHONUNBUFFERED = '1'
    }

    stages {
        stage('Setup') {
            steps {
                bat '''
                python -m pip install --upgrade pip
                pip install -r requirements.txt
                '''
            }
        }

        stage('Daily Health Check') {
            steps {
                // Matches the AmazonWebServicesCredentialsBinding convention used by the
                // other client Jenkinsfiles (DailyChecksFramework / SingleClientChecks).
                withCredentials([
                    [$class: 'AmazonWebServicesCredentialsBinding', credentialsId: 'aws-master-account']
                ]) {
                    bat "python -u main.py --client %CLIENT_NAME%"
                }
            }
        }
    }

    post {
        always {
            archiveArtifacts artifacts: 'output/**/*.html', allowEmptyArchive: true
        }
    }
}

