pipeline {
    agent any

    options {
        timestamps()
        timeout(time: 30, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '30', artifactNumToKeepStr: '30'))
    }

    // Scheduled for twice-daily execution; adjust cron as required per environment.
    triggers {
        cron('0 6,18 * * *')
    }

    parameters {
        // Optional override. If left blank, main.py resolves the client from $CLIENT_NAME
        // or, failing that, this job's own name (e.g. job "combined_mgl" -> client "mgl") -
        // matching the one-job-per-client convention already used for combined_fleetcor.
        // Onboarding a new client (MGL, BHFS, ...) is then just: add clients/<name>.yaml,
        // create a Jenkins job named "combined_<name>" pointing at this same Jenkinsfile.
        string(name: 'CLIENT_NAME', defaultValue: '', description: 'Client to check (optional - inferred from the job name if blank)')
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
                    bat 'python -u main.py'
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

