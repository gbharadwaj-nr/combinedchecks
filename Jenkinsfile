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
        // "auto" (default) infers the client from this job's name (e.g. job
        // "combined_mgl" -> client "mgl"), matching the one-job-per-client
        // convention already used for combined_fleetcor. Pick an explicit
        // client to override that, e.g. when testing one client's checks
        // from a different job. Onboarding a new client: add clients/<name>.yaml,
        // add "<name>" to the choices list below, and create a Jenkins job
        // named "combined_<name>" pointing at this same Jenkinsfile.
        choice(
            name: 'CLIENT_NAME',
            choices: ['auto', 'fleetcor', 'mgl', 'bhfs'],
            description: 'Client to check ("auto" infers it from this job\'s name)'
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

