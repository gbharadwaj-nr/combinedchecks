"""Sample CheckResult data used only by `main.py --dry-run`.

This lets the reporting pipeline (rendering + output layout) be validated
without live AWS credentials - no AWS/HTTP/DB calls are made.
"""
from checks.base import CheckResult, Status


def build_demo_results():
    return [
        CheckResult(key="rds", title="RDS Availability / Status", category="infrastructure",
                    status=Status.HEALTHY,
                    summary="2 RDS resource(s) checked; worst storage health = HEALTHY"),
        CheckResult(key="ec2", title="EC2 Instance and System Health", category="infrastructure",
                    status=Status.HEALTHY,
                    summary="3 instance(s) checked; worst health = HEALTHY"),
        CheckResult(key="dxv", title="DXV Instance Availability", category="infrastructure",
                    status=Status.NOT_PRESENT, summary="DXV: Not Present"),
        CheckResult(key="asg", title="ASG Health", category="infrastructure",
                    status=Status.NOT_PRESENT, summary="ASG: Not Present"),
        CheckResult(key="kafka", title="Kafka Consumer Details", category="infrastructure",
                    status=Status.NOT_PRESENT, summary="Kafka: Not Present"),
        CheckResult(key="cloudwatch", title="CloudWatch API Health", category="infrastructure",
                    status=Status.HEALTHY, summary="CloudWatch API Health: HEALTHY"),
        CheckResult(key="ui", title="UI / Application Availability", category="application",
                    status=Status.HEALTHY, summary="All 1 endpoint(s) available"),
        CheckResult(key="database", title="Database Connection Health", category="application",
                    status=Status.NOT_CONFIGURED, summary="Database Connection: Not Configured"),
        CheckResult(key="watchlist", title="Watchlist Import Completion", category="batch",
                    status=Status.COMPLETED,
                    summary="Checked 1 watchlist source(s) (World-Check); worst status = COMPLETED"),
        CheckResult(key="batch_file", title="Batch File Acquisition / Receipt", category="batch",
                    status=Status.COMPLETED,
                    summary="Checked 1 batch(es) (Daily Transaction File); worst status = COMPLETED"),
        CheckResult(key="wlm", title="WLM / Screening Batch Completion", category="batch",
                    status=Status.NOT_PRESENT, summary="WLM / Screening Batch: Not Present"),
        CheckResult(key="aml", title="AML Batch Completion", category="batch",
                    status=Status.NOT_PRESENT, summary="AML Batch: Not Present"),
        CheckResult(key="cdd", title="CDD Completion / Consistency", category="batch",
                    status=Status.NOT_PRESENT, summary="CDD: Not Present"),
        CheckResult(key="overrun", title="Batch Failure / Overrun", category="batch",
                    status=Status.HEALTHY,
                    summary="Checked 1 batch(es) for overrun; worst status = HEALTHY"),
    ]
