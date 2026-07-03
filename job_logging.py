"""Stub raportowania jobów ETL — zastępuje firmowy moduł logowanie.py poza środowiskiem Windows."""


def Job_success(job_name):
    pass


def Job_failed(job_name, exc):
    raise exc
