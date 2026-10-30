from procintel.core import llm


def _env(monkeypatch, **kv):
    for k in ("MODEL", "API_BASE", "API_KEY", "EXTRA_BODY"):
        for p in ("LLM", "BATCH"):
            monkeypatch.delenv(f"PROCINTEL_{p}_{k}", raising=False)
    for k, v in kv.items():
        monkeypatch.setenv(k, v)


def test_with_no_batch_model_jobs_use_the_answer_model(monkeypatch):
    _env(monkeypatch, PROCINTEL_LLM_MODEL="openai/saluki", PROCINTEL_LLM_API_BASE="http://a/v1", PROCINTEL_LLM_API_KEY="k1")
    with llm.use_batch():
        args = llm._request("s", "u", None, None, llm.ANSWER, {})
    assert (args["model"], args["api_base"], args["api_key"]) == ("openai/saluki", "http://a/v1", "k1")
    assert not llm.batch_dedicated()


def test_a_batch_endpoint_takes_over_inside_a_job_only(monkeypatch):
    _env(monkeypatch, PROCINTEL_LLM_MODEL="openai/saluki", PROCINTEL_LLM_API_BASE="http://a/v1", PROCINTEL_LLM_API_KEY="k1",
         PROCINTEL_BATCH_API_BASE="http://b/v1")
    assert llm.batch_dedicated()
    with llm.use_batch():
        args = llm._request("s", "u", None, None, llm.ANSWER, {})
        judge = llm._request("s", "u", None, None, llm.JUDGE, {}) if llm.available(llm.JUDGE) else None
    assert args["api_base"] == "http://b/v1" and args["model"] == "openai/saluki"   # same model name, other server
    assert args["api_key"] is None                                                    # the answer endpoint's key is not sent elsewhere
    assert judge is None
    after = llm._request("s", "u", None, None, llm.ANSWER, {})
    assert after["api_base"] == "http://a/v1" and after["api_key"] == "k1"           # a user's request is unaffected


def test_batch_key_model_and_options_are_used_together(monkeypatch):
    _env(monkeypatch, PROCINTEL_LLM_MODEL="openai/saluki", PROCINTEL_LLM_EXTRA_BODY='{"x": 1}',
         PROCINTEL_BATCH_MODEL="openai/small", PROCINTEL_BATCH_API_BASE="http://b/v1", PROCINTEL_BATCH_API_KEY="k2")
    with llm.use_batch():
        args = llm._request("s", "u", None, None, llm.ANSWER, {})
    assert (args["model"], args["api_base"], args["api_key"]) == ("openai/small", "http://b/v1", "k2")
    assert "extra_body" not in args                                                   # options for the answer model stay with it
