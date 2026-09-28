"""Django의 DB 격리에 Evennia worker 초기화와 실패 정보 전달을 더한다."""

import os
from unittest.suite import _ErrorHolder

import django
from django.conf import settings
from django.test.runner import ParallelTestSuite, RemoteTestResult, RemoteTestRunner
from evennia.server.tests.testrunner import EvenniaTestSuiteRunner


def setup_evennia_worker():
    # Windows spawn은 부모의 Evennia 초기화를 상속하지 않는다.
    django.setup()
    import evennia

    evennia._init()
    settings.TEST_ENVIRONMENT = True


class PrimalRemoteTestResult(RemoteTestResult):
    def addSubTest(self, test, subtest, err):
        if err is not None:
            # 테스트 객체의 Evennia cache/Mock를 전송하지 않는다. 조건과 traceback은 보존한다.
            summary = _ErrorHolder(subtest.id())
            summary.failureException = subtest.failureException
            subtest = summary
        super().addSubTest(test, subtest, err)


class PrimalRemoteTestRunner(RemoteTestRunner):
    resultclass = PrimalRemoteTestResult


class PrimalParallelTestSuite(ParallelTestSuite):
    process_setup = setup_evennia_worker
    runner_class = PrimalRemoteTestRunner


class PrimalTestRunner(EvenniaTestSuiteRunner):
    parallel_test_suite = PrimalParallelTestSuite

    def setup_test_environment(self, **kwargs):
        # Evennia의 --settings 파일명은 Django argv 처리 중 환경변수에 그대로 남는다.
        # spawn worker에는 부모가 실제로 로드한 정규 모듈 경로를 전달한다.
        self._previous_settings_module = os.environ.get("DJANGO_SETTINGS_MODULE")
        os.environ["DJANGO_SETTINGS_MODULE"] = settings.SETTINGS_MODULE
        super().setup_test_environment(**kwargs)

    def teardown_test_environment(self, **kwargs):
        try:
            super().teardown_test_environment(**kwargs)
        finally:
            if self._previous_settings_module is None:
                os.environ.pop("DJANGO_SETTINGS_MODULE", None)
            else:
                os.environ["DJANGO_SETTINGS_MODULE"] = self._previous_settings_module
