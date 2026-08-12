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
        // Jenkins `choice` parameters default to the FIRST entry, so "fleetcor"
        // is the default here - this makes the job work out of the box
        // regardless of what the Jenkins job itself is named (e.g. "Daily_Checks").
        // Pick "auto" instead to infer the client from this job's name (e.g. job
        // "combined_mgl" -> client "mgl"), for jobs that follow that convention.
        // Onboarding a new client: add clients/<name>.yaml, add "<name>" to the
        // choices list below, and create/point a Jenkins job at this Jenkinsfile.
        choice(
            name: 'CLIENT_NAME',
            choices: ['fleetcor', 'mgl', 'bhfs', 'auto'],
            description: 'Client to check (default: fleetcor - pick "auto" to infer it from this job\'s name)'
        )
    }

    environment {
        PYTHONUNBUFFERED = '1'
    }

    stages {
        stage('Setup') {
            steps {
                // Guarantees archiveArtifacts only picks up this build's report, even if
                // old output/ files were ever committed or left over from a prior build.
                bat 'if exist output rmdir /s /q output'
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
                    bat '''
                    if "%CLIENT_NAME%"=="auto" (
                        python -u main.py
                    ) else (
                        python -u main.py --client %CLIENT_NAME%
                    )
                    '''
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

