"""Clientes dos dois modelos do pipeline, via REST: o Jev (TypeSafe), que decide o tema, e um LLM barato
que revisa (GPT-6 Luna, pelo OpenRouter).

Toda resposta é gravada em cache/<jev|llm>/<sha256 da requisição>.json, que vai para o repositório: o
publicacao.csv pode ser regenerado sem nenhuma chave de API. A requisição em si (que contém o texto
das questões, dado da empresa) fica em cache_req/, fora do git. Com run_all.py --chave, nada do cache/ é
reaproveitado: as respostas novas vão para cache_ao_vivo/<data-hora>/ (ver modo_ao_vivo).

Provedor: por padrão o backend local (JEV_BASE_URL). Se ele não responder como API do Jev, ou com
JEV_PROVIDER=openrouter, usa o Jev do OpenRouter (POST /api/v1/systemone) com a OPENROUTER_API_KEY.
A versão é fixa nos dois provedores (a TypeSafe recomenda fixar quando há limiares calibrados).
"""
import json
import sys
import time

import httpx

from common import CACHE, ROOT, env, sha

OPENROUTER = "https://openrouter.ai/api/v1"
PRECO_POR_TOKEN = 0.042 / 1e6          # US$ por token de entrada; a saída é grátis
CUSTO_AO_VIVO = 0.75                   # US$ de uma rodada inteira sem cache (Jev ~0,67 + revisor ~0,07), medido
# jev_usd: custo de todas as respostas usadas (inclusive as do cache, já pagas antes); jev_usd_novo: só o desta execução
USAGE = {"jev_usd": 0.0, "jev_usd_novo": 0.0, "jev_tokens": 0, "calls": 0, "cache_hits": 0}
PASTAS = {"resp": CACHE, "req": ROOT / "cache_req"}


def modo_ao_vivo():
    """run_all.py --chave: nada do cache/ do repositório é reaproveitado. As respostas novas vão para
    cache_ao_vivo/<data-hora>/ (fora do git), e o cache/ entregue fica intacto."""
    pasta = ROOT / "cache_ao_vivo" / time.strftime("%Y%m%d-%H%M%S")
    PASTAS.update(resp=pasta / "cache", req=pasta / "cache_req")
    return pasta


def credito_disponivel():
    """Saldo na OpenRouter em US$ (o menor entre o da conta e o limite da chave, se houver); None se não der
    para consultar. Levanta RuntimeError se a OpenRouter recusar a chave."""
    cab = {"Authorization": f"Bearer {env('OPENROUTER_API_KEY')}"}
    try:
        r = _http.get(f"{OPENROUTER}/key", headers=cab)
        if r.status_code == 401:
            raise RuntimeError("a OpenRouter recusou a chave (401); confira se ela foi copiada inteira")
        limite = r.json()["data"].get("limit_remaining")
        conta = _http.get(f"{OPENROUTER}/credits", headers=cab).json()["data"]
        saldo = conta["total_credits"] - conta["total_usage"]
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        return None
    return saldo if limite is None else min(saldo, limite)


def cached(kind, payload, fn):
    key = sha(payload)
    path = PASTAS["resp"] / kind / f"{key}.json"
    if path.exists():
        USAGE["cache_hits"] += 1
        return json.loads(path.read_text(encoding="utf-8"))["response"]
    response = fn()
    for base, obj in ((PASTAS["resp"], {"key": key, "response": response}), (PASTAS["req"], {"key": key, "request": payload})):
        p = base / kind / f"{key}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    USAGE["calls"] += 1
    return response


_http = httpx.Client(timeout=180)
_provider = None   # decidido na primeira chamada


def _post(url, body, headers, tries=7):
    for i in range(tries):
        try:
            r = _http.post(url, json=body, headers=headers)
        except httpx.TransportError:
            if i == tries - 1:
                raise
            time.sleep(2 ** i)
            continue
        if r.status_code in (429, 500, 502, 503, 504, 529) and i < tries - 1:
            time.sleep(float(r.headers.get("retry-after", 2 ** i)))
            continue
        if r.status_code >= 400:
            raise RuntimeError(f"{url} -> {r.status_code}: {r.text[:500]}")
        return r.json()


def _alvo(provider):
    if provider == "openrouter":
        key = env("OPENROUTER_API_KEY")
        if not key:
            raise RuntimeError("Defina OPENROUTER_API_KEY no arquivo .env (veja .env.example)")
        return (f"{OPENROUTER}/systemone", {"Authorization": f"Bearer {key}"},
                env("JEV_MODEL_OPENROUTER", "typesafe/jev-1.13-20260917"))
    url = env("JEV_BASE_URL", "http://localhost:3010").rstrip("/") + env("JEV_PATH", "/api/v1/decisions")
    headers = {"Authorization": f"Bearer {env('JEV_API_KEY')}"} if env("JEV_API_KEY") else {}
    return url, headers, env("JEV_MODEL", "jev-1.13.0")


def _chamar(state, questions, idem):
    global _provider
    if _provider is None:
        _provider = env("JEV_PROVIDER", "openrouter")
    if _provider == "backend":
        url, headers, model = _alvo("backend")
        try:
            resp = _post(url, {"model": model, "state": state, "questions": questions},
                         {**headers, "Idempotency-Key": idem}, tries=2)
            if isinstance(resp, dict) and "answers" in resp:
                return resp
            motivo = "resposta sem 'answers'"
        except (httpx.TransportError, RuntimeError, ValueError) as e:
            motivo = str(e)[:120]
        print(f"[jev] backend local indisponível ({motivo}); usando o Jev do OpenRouter", file=sys.stderr)
        _provider = "openrouter"
    url, headers, model = _alvo("openrouter")
    return _post(url, {"model": model, "state": state, "questions": questions},
                 {**headers, "Idempotency-Key": idem})


def llm_json(model, system, user, schema, max_tokens=800):
    """LLM com saída em JSON Schema estrito, pelo OpenRouter (chat completions). Mesmo cache em disco do Jev.
    Usado só pelo revisor automático (s05d)."""
    payload = {"model": model, "system": system, "user": user, "schema": schema, "max_tokens": max_tokens}

    def chamar():
        key = env("OPENROUTER_API_KEY")
        if not key:
            raise RuntimeError("Defina OPENROUTER_API_KEY no arquivo .env")
        sistema = system
        if model.startswith("anthropic/"):            # cache de prompt explícito: a lista de temas se repete
            sistema = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
        body = {"model": model, "temperature": 0, "max_tokens": max_tokens, "usage": {"include": True},
                "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": user}],
                "response_format": {"type": "json_schema",
                                    "json_schema": {"name": "revisao", "strict": True, "schema": schema}}}
        for tentativa in range(3):                 # JSON cortado (limite de tokens): tenta de novo com mais espaço
            r = _post(f"{OPENROUTER}/chat/completions", body, {"Authorization": f"Bearer {key}", "X-Title": "case-vicio-ia"})
            if "choices" not in r:                 # erro do provedor dentro de um 200: espera e tenta de novo
                time.sleep(3 * (tentativa + 1))
                msg = str(r.get("error"))
                continue
            msg = r["choices"][0]["message"]["content"] or ""
            try:
                return {"parsed": json.loads(msg), "usage": r.get("usage") or {}, "model": r.get("model")}
            except json.JSONDecodeError:
                body["max_tokens"] *= 2
        raise RuntimeError(f"{model}: JSON inválido depois de 3 tentativas: {msg[:200]}")

    antes = USAGE["calls"]
    resp = cached("llm", payload, chamar)
    custo = (resp.get("usage") or {}).get("cost") or 0
    USAGE["llm_usd"] = USAGE.get("llm_usd", 0) + custo
    if USAGE["calls"] > antes:
        USAGE["llm_usd_novo"] = USAGE.get("llm_usd_novo", 0) + custo
    return resp["parsed"], resp.get("usage") or {}


def jev(state, questions):
    """Envia state + perguntas tipadas (choice/noul) e devolve as respostas normalizadas:
    {"answers": {nome: {"type": "choice", "choice", "probabilities", "confidence"}
                       | {"type": "noul", "noul"}}, "model": versão}
    """
    # Chave do cache com o nome canônico do modelo: mesma pergunta à mesma versão = mesma decisão,
    # venha do backend local ou do OpenRouter.
    canon = {"model": "jev-1.13.0", "state": state, "questions": questions}
    antes = USAGE["calls"]
    resp = cached("jev", canon, lambda: _chamar(state, questions, sha(canon)))
    usage = resp.get("usage") or {}
    tokens = usage.get("input_tokens") or usage.get("prompt_tokens") or 0
    custo = usage.get("cost_usd") or usage.get("cost") or tokens * PRECO_POR_TOKEN
    USAGE["jev_tokens"] += tokens
    USAGE["jev_usd"] += custo
    if USAGE["calls"] > antes:
        USAGE["jev_usd_novo"] += custo
    answers = {}
    for name, a in (resp.get("answers") or {}).items():
        if "noul" in a:
            answers[name] = {"type": "noul", "noul": float(a["noul"])}
        else:
            answers[name] = {"type": "choice", "choice": a["choice"],
                             "probabilities": a["probabilities"], "confidence": a.get("confidence")}
    return {"answers": answers, "model": resp.get("model")}
