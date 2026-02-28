import json
from pathlib import Path
import re
import unicodedata
import pandas as pd
import requests
import streamlit as st

# ============ CONFIGURAÇÃO ============
OLLAMA_HOST = "http://localhost:11434"
OLLAMA_URL = f"{OLLAMA_HOST}/api/generate"
MODELO = "gpt-oss"


def _resolver_modelo_ollama() -> str:
    if "_ollama_modelo" in st.session_state:
        return st.session_state["_ollama_modelo"]

    try:
        r = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
        if r.ok:
            payload = r.json() if r.content else {}
            modelos = [m.get("name") for m in payload.get("models", []) if isinstance(m, dict)]
            modelos = [m for m in modelos if isinstance(m, str) and m.strip()]

            escolhido = MODELO
            if MODELO not in modelos:
                candidatos = [m for m in modelos if m.startswith(MODELO + ":") or MODELO in m]
                if candidatos:
                    escolhido = candidatos[0]
                elif modelos:
                    escolhido = modelos[0]

            st.session_state["_ollama_modelo"] = escolhido
            return escolhido
    except requests.exceptions.RequestException:
        pass

    st.session_state["_ollama_modelo"] = MODELO
    return MODELO

# ============ CARREGAR DADOS ============
BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"

with (DATA_DIR / "perfil_investidor.json").open("r", encoding="utf-8") as f:
    perfil = json.load(f)

transacoes = pd.read_csv(DATA_DIR / "transacoes.csv")
historico = pd.read_csv(DATA_DIR / "historico_atendimento.csv")

with (DATA_DIR / "produtos_financeiros.json").open("r", encoding="utf-8") as f:
    produtos = json.load(f)

# ============ CONTEXTO MONTADO ============
def _montar_contexto_resumido() -> str:
    metas_txt = ""
    metas = perfil.get("metas")
    if isinstance(metas, list) and metas:
        partes = []
        for m in metas[:5]:
            if not isinstance(m, dict):
                continue
            meta = m.get("meta")
            valor = m.get("valor_necessario")
            prazo = m.get("prazo")
            partes.append(f"- {meta} | R$ {valor} | prazo {prazo}")
        if partes:
            metas_txt = "\n".join(partes)

    transacoes_rec = transacoes.tail(5)
    historico_rec = historico.tail(3)

    # Produtos: manter como catálogo para explicação (sem forçar recomendação)
    produtos_linhas = []
    if isinstance(produtos, list):
        for p in produtos[:10]:
            if not isinstance(p, dict):
                continue
            produtos_linhas.append(
                f"- {p.get('nome')} | cat: {p.get('categoria')} | risco: {p.get('risco')} | aporte mín.: {p.get('aporte_minimo')}"
            )

    produtos_txt = "\n".join(produtos_linhas) if produtos_linhas else "(não informado)"

    return f"""
CLIENTE (resumo): {perfil.get('nome')}, {perfil.get('idade')} anos, profissão {perfil.get('profissao')}
PERFIL: {perfil.get('perfil_investidor')} | renda mensal: R$ {perfil.get('renda_mensal')} | aceita risco: {perfil.get('aceita_risco')}
OBJETIVO PRINCIPAL: {perfil.get('objetivo_principal')}
PATRIMÔNIO: R$ {perfil.get('patrimonio_total')} | RESERVA: R$ {perfil.get('reserva_emergencia_atual')}

METAS:
{metas_txt or "(não informado)"}

TRANSAÇÕES (últimas 5):
{transacoes_rec.to_string(index=False)}

ATENDIMENTOS (últimos 3):
{historico_rec.to_string(index=False)}

CATÁLOGO DE PRODUTOS (para explicar como funcionam):
{produtos_txt}
""".strip()


def _normalizar_texto(s: str) -> str:
    s = (s or "").strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^a-z0-9\s\?]", "", s)
    return s.strip()


def _eh_saudacao(msg: str) -> bool:
    t = _normalizar_texto(msg)
    if not t:
        return False
    if "?" in t:
        return False
    # Saudações curtas e comuns
    sauds = {
        "oi",
        "ola",
        "eai",
        "bom dia",
        "boa tarde",
        "boa noite",
        "hello",
        "hi",
    }
    if t in sauds:
        return True
    return any(t.startswith(s + " ") for s in sauds)

# ============ SYSTEM PROMPT ============
SYSTEM_PROMPT = """Você é o MIA, um educador financeiro amigável e didático.

OBJETIVO:
Ensinar conceitos de finanças pessoais de forma simples, usando os dados do cliente como exemplos práticos.

REGRAS:
- NUNCA recomende investimentos específicos, apenas explique como funcionam;
- JAMAIS responda a perguntas fora do tema ensino de finanças pessoais. Quando ocorrer, responda lembrando o seu papel de educador financeiro;
- Use os dados fornecidos apenas quando forem relevantes para a pergunta, e prefira exemplos curtos;
- Não comece listando dados do cliente; primeiro entenda o que a pessoa quer aprender;
- Linguagem simples, como se explicasse para um amigo;
- Se não souber algo, admita: "Não tenho essa informação, mas posso explicar...";
- Sempre pergunte se o cliente entendeu;
- Responda de forma sucinta e direta, com no máximo 3 parágrafos.
"""

# ============ CHAMAR OLLAMA ============
def perguntar(msg):
    if _eh_saudacao(msg):
        return (
            "Olá! Eu sou a MIA, sua educadora financeira. "
            "O que você quer aprender hoje?\n\n"
            "Exemplos: orçamento do mês, reserva de emergência, dívidas, metas, renda fixa vs variável."
        )

    contexto = _montar_contexto_resumido()
    prompt = f"""
    {SYSTEM_PROMPT}

    CONTEXTO DO CLIENTE:
    {contexto}

    Pergunta: {msg}"""

    modelo = _resolver_modelo_ollama()
    try:
        r = requests.post(
            OLLAMA_URL,
            json={"model": modelo, "prompt": prompt, "stream": False},
            timeout=60,
        )
    except requests.exceptions.RequestException as exc:
        return (
            "Não consegui consultar o Ollama agora. "
            "Confira se ele está rodando e tente novamente. "
            f"Detalhes: {exc}"
        )

    if not r.ok:
        detalhe = ""
        try:
            payload = r.json() if r.content else {}
            if isinstance(payload, dict) and isinstance(payload.get("error"), str):
                detalhe = payload["error"]
            else:
                detalhe = json.dumps(payload, ensure_ascii=False)
        except ValueError:
            detalhe = (r.text or "").strip()

        if len(detalhe) > 400:
            detalhe = detalhe[:400] + "..."

        return (
            f"Erro ao consultar o Ollama (HTTP {r.status_code}). "
            f"Modelo: '{modelo}'. Detalhes: {detalhe}"
        )

    try:
        data = r.json()
    except ValueError:
        texto = (r.text or "").strip()
        if len(texto) > 500:
            texto = texto[:500] + "..."
        return (
            "Recebi uma resposta inválida do Ollama (não-JSON). "
            f"Status: {r.status_code}. Corpo: {texto}"
        )

    if isinstance(data, dict) and isinstance(data.get("response"), str):
        return data["response"].strip()

    if isinstance(data, dict) and isinstance(data.get("error"), str):
        return (
            f"Erro do Ollama: {data['error']}. "
            f"Verifique se o modelo '{MODELO}' está instalado (`ollama pull {MODELO}`)."
        )

    return "Resposta inesperada do Ollama: " + json.dumps(data, ensure_ascii=False)

# ============ INTERFACE ============
st.title("🎓 MIA, seu Educador Financeiro")

if "mensagens" not in st.session_state:
    st.session_state["mensagens"] = [
        {
            "role": "assistant",
            "content": (
                "Olá! Eu sou a MIA, sua educadora financeira. "
                "Me diga o que você quer entender hoje (ex.: orçamento, reserva, dívidas, metas)."
            ),
        }
    ]

for m in st.session_state["mensagens"]:
    st.chat_message(m["role"]).write(m["content"])

if pergunta := st.chat_input("Sua dúvida sobre finanças..."):
    st.session_state["mensagens"].append({"role": "user", "content": pergunta})
    st.chat_message("user").write(pergunta)
    with st.spinner("..."):
        resposta = perguntar(pergunta)
    st.session_state["mensagens"].append({"role": "assistant", "content": resposta})
    st.chat_message("assistant").write(resposta)
