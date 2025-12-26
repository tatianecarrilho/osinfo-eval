# 🔧 Guia de Solução de Problemas

## BigQuery Desabilitado

### ❌ Problema: "BIGQUERY_CREDENTIALS_PATH não está configurado no arquivo .env"

**Solução:**

1. Abra o arquivo `.env` na raiz do projeto
2. Adicione a linha:
   ```bash
   BIGQUERY_CREDENTIALS_PATH=rj-nf-agent-tati.json
   ```
3. Salve o arquivo
4. Reinicie a aplicação Streamlit

**Seu `.env` deve ter pelo menos:**
```bash
# Gemini
GEMINI_API_KEY=sua_chave_aqui

# BigQuery
BIGQUERY_CREDENTIALS_PATH=rj-nf-agent-tati.json
```

---

### ❌ Problema: "Arquivo de credenciais não encontrado"

**Solução:**

1. Verifique se o arquivo `rj-nf-agent-tati.json` está na raiz do projeto:
   ```bash
   ls -la rj-nf-agent-tati.json
   ```

2. Se não estiver, obtenha o arquivo de credenciais do BigQuery

3. Coloque o arquivo na raiz do projeto (mesmo diretório do `app.py`)

4. Verifique o caminho no `.env`:
   ```bash
   BIGQUERY_CREDENTIALS_PATH=rj-nf-agent-tati.json
   ```

---

### ❌ Problema: "Biblioteca google-cloud-bigquery não instalada"

**Solução:**

Execute:
```bash
pip install google-cloud-bigquery db-dtypes
```

Ou reinstale todas as dependências:
```bash
pip install -r requirements.txt
```

---

## Problemas com Gemini AI

### ❌ Problema: "GEMINI_API_KEY não encontrada"

**Solução:**

1. Crie/edite o arquivo `.env` na raiz do projeto

2. Adicione sua chave:
   ```bash
   GEMINI_API_KEY=sua_chave_api_aqui
   ```

3. Obtenha sua chave em: https://makersuite.google.com/app/apikey

4. Reinicie a aplicação

---

### ❌ Problema: "Erro na API: status 400/401/403"

**Possíveis causas e soluções:**

- **400 (Bad Request)**: Modelo inválido
  - Verifique o modelo no `config.py` ou `.env`
  - Modelos válidos: `gemini-1.5-flash`, `gemini-1.5-pro`, `gemini-2.0-flash-exp`

- **401 (Unauthorized)**: Chave de API inválida
  - Verifique se a chave está correta no `.env`
  - Gere uma nova chave se necessário

- **403 (Forbidden)**: Sem permissão
  - Verifique se a API do Gemini está habilitada no seu projeto Google Cloud
  - Verifique cotas e limites da API

---

## Problemas com Upload de PDF

### ❌ Problema: "Documento muito grande para análise"

**Solução:**

O limite padrão é 100 MB. Para aumentar:

1. Edite `config.py`:
   ```python
   LIMITE_TAMANHO_PDF_MB = 150  # Novo limite
   ```

2. Reinicie a aplicação

**Nota:** PDFs muito grandes podem causar timeout na API do Gemini.

---

### ❌ Problema: "Timeout ao processar documento"

**Soluções:**

1. **Aumentar timeout** - Edite `config.py`:
   ```python
   TIMEOUT_API_SEGUNDOS = 180  # 3 minutos
   ```

2. **Reduzir tamanho do PDF**:
   - Comprima o PDF antes do upload
   - Divida PDFs muito grandes em partes menores

3. **Usar modelo mais rápido**:
   ```python
   GEMINI_MODEL = "gemini-1.5-flash"  # Mais rápido que pro
   ```

---

## Problemas Gerais

### ❌ Problema: Aplicação não abre no navegador

**Soluções:**

1. Acesse manualmente: http://localhost:8501

2. Use porta diferente:
   ```bash
   streamlit run app.py --server.port 8080
   ```

3. Verifique se a porta está em uso:
   ```bash
   lsof -i :8501
   ```

---

### ❌ Problema: "ModuleNotFoundError"

**Solução:**

Instale todas as dependências:
```bash
pip install -r requirements.txt
```

Dependências principais:
- streamlit
- python-dotenv
- requests
- PyPDF2
- pandas
- openpyxl
- google-cloud-bigquery
- db-dtypes

---

## Verificação Rápida (Checklist)

Antes de executar a aplicação, verifique:

- [ ] Arquivo `.env` existe na raiz
- [ ] `GEMINI_API_KEY` está configurado no `.env`
- [ ] `BIGQUERY_CREDENTIALS_PATH` está configurado no `.env` (se usar BigQuery)
- [ ] Arquivo de credenciais JSON existe na raiz (se usar BigQuery)
- [ ] Todas as dependências instaladas: `pip install -r requirements.txt`
- [ ] Python 3.8+ instalado: `python --version`

---

## Como Reiniciar a Aplicação Streamlit

1. No terminal onde o Streamlit está rodando, pressione `Ctrl+C`

2. Execute novamente:
   ```bash
   streamlit run app.py
   ```

**Ou** use o botão "Rerun" na interface do Streamlit (canto superior direito)

---

## Logs e Debug

### Ver logs detalhados

Execute com modo verbose:
```bash
streamlit run app.py --logger.level=debug
```

### Limpar cache do Streamlit

Se a aplicação estiver com comportamento estranho:
```bash
streamlit cache clear
```

---

## Ainda com problemas?

1. Verifique se todas as configurações em `config.py` estão corretas

2. Compare seu `.env` com o `.env.example`

3. Teste o script em lote primeiro:
   ```bash
   python extrair_notas_fiscais.py
   ```
   Se funcionar, o problema é específico do Streamlit

4. Verifique a documentação completa: [APP_README.md](APP_README.md)
