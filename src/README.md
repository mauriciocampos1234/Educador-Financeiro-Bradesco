# Passo a Passo de Execução

## Setup do Ollama

```bash
# 1. Instalar Ollama (ollama.com)
# 2. Baixar um modelo leve
ollama pull gpt-oss

# 3. Testar se funciona
ollama run gpt-oss "Olá!"
```

## Código Completo

Todo o código-fonte está no arquivo `app.py`.

## Como Rodar

```bash
# 1. Instalar dependências
python -m pip install streamlit pandas requests

# 2. Garantir que Ollama está rodando
ollama serve

# 3. Rodar o app
python -m streamlit run .\src\app.py

# (Se o comando `streamlit` estiver disponível no seu PATH, isso também funciona)
# streamlit run .\src\app.py
```

## Evidência de Execução

<img width="1920" height="1107" alt="image" src="https://github.com/user-attachments/assets/60feed79-38a6-43dc-b23a-9dd007e34c1d" />
