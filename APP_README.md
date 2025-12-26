# 📄 Aplicação Web - Análise de Notas Fiscais

Interface web desenvolvida com Streamlit para análise individual de PDFs de prestação de contas.

## 🚀 Como Executar

### 1. Instale as dependências (se ainda não instalou)

```bash
pip install -r requirements.txt
```

### 2. Configure o arquivo `.env`

Certifique-se de que o arquivo `.env` está configurado com:

```bash
GEMINI_API_KEY=sua_chave_api_aqui
BIGQUERY_CREDENTIALS_PATH=rj-nf-agent-tati.json  # Opcional
```

### 3. Execute a aplicação

```bash
streamlit run app.py
```

A aplicação abrirá automaticamente no seu navegador em `http://localhost:8501`

## 📋 Funcionalidades

### 1️⃣ Upload de PDF
- Faça upload de um arquivo PDF (máximo 100 MB)
- Visualize informações básicas: nome, tamanho, número de páginas

### 2️⃣ Análise Automática
- **Gemini AI**: Extrai informações das notas fiscais do PDF
  - Número da página
  - CNPJ do prestador
  - Tipo de documento
  - Número da NF
  - Valor total

- **BigQuery** (opcional): Consulta dados declarados em despesas
  - Exibe TODOS os registros encontrados para o arquivo
  - Número do documento
  - Valor do documento
  - Valor pago total
  - Indica se houve matching entre NF extraída e registro do BigQuery

### 3️⃣ Validações Automáticas
O sistema realiza três validações:

1. **PDF possui NF em Despesas?**
   - ✅ SIM: NF encontrada no BigQuery
   - ❌ NÃO: NF não encontrada

2. **Valor Pago ≤ Valor Declarado?**
   - ✅ SIM: Valor pago menor ou igual ao declarado
   - ❌ NÃO: Valor pago maior que o declarado

3. **Valor NF = Valor Declarado?**
   - ✅ SIM: Valores coincidem (tolerância de R$ 0,01)
   - ❌ NÃO: Valores divergem

### 4️⃣ Classificação Final

- **✅ Descartado**: Todas as validações OK
- **⚠️ Suspeito**: Pelo menos uma validação falhou
- **❓ Não foi possível analisar**: Erro no processamento

### 5️⃣ Exportação
- Baixe os resultados em formato Excel (.xlsx)
- Arquivo contém todas as informações extraídas e validações

## 🎨 Interface

### Tela Principal
```
┌─────────────────────────────────────────────┐
│  📄 Análise de Notas Fiscais com IA        │
├─────────────────────────────────────────────┤
│  1️⃣ Upload do PDF                          │
│     [Arraste ou clique para upload]        │
│                                             │
│  2️⃣ Processamento                          │
│     [🚀 Analisar PDF]                      │
│                                             │
│     🤖 Análise com Gemini AI               │
│     ✅ Encontradas X nota(s) fiscal(is)    │
│                                             │
│     📊 Consulta ao BigQuery                │
│     ✅ Encontrados X registro(s)           │
│     🔍 Ver todos os registros (tabela)     │
│                                             │
│  3️⃣ Resultados da Análise                  │
│     📋 Nota Fiscal #1                      │
│        ✅ Classificação: Descartado        │
│        📄 Dados Extraídos (Gemini)         │
│        🗄️ Dados do BigQuery                │
│           🎯 Matching encontrado (ou ⚠️)   │
│        ✅ Validações                        │
│                                             │
│  4️⃣ Exportar Resultados                    │
│     [📥 Download Excel]                    │
└─────────────────────────────────────────────┘
```

### Sidebar (Barra Lateral)
```
┌─────────────────────────┐
│  ℹ️ Informações         │
├─────────────────────────┤
│  Configurações Atuais:  │
│  • Modelo: gemini-...   │
│  • Limite: 100 MB       │
│  • BigQuery: ✅         │
│                         │
│  BigQuery:              │
│  • Projeto: rj-nf...    │
│  • Dataset: poc_...     │
│  • Tabela: despesas...  │
└─────────────────────────┘
```

## 🔧 Configurações

A aplicação utiliza as mesmas configurações do script em lote:

- **[config.py](config.py)**: Configurações gerais do projeto
- **[.env](.env)**: Credenciais e variáveis de ambiente

## 📊 Diferenças entre App Web e Script em Lote

| Característica | App Web (`app.py`) | Script Lote (`extrair_notas_fiscais.py`) |
|----------------|-------------------|------------------------------------------|
| **Interface** | Interface web interativa | Linha de comando |
| **Entrada** | Upload de 1 PDF por vez | Processa pasta com múltiplos PDFs |
| **Saída** | Visualização na tela + download | Arquivo Excel na pasta `results/` |
| **Uso** | Análise pontual e exploratória | Processamento em massa |
| **Feedback** | Tempo real com progresso visual | Logs no terminal |

## ⚙️ Configurações Avançadas

### Personalizar Porta

Por padrão, o Streamlit roda na porta 8501. Para mudar:

```bash
streamlit run app.py --server.port 8080
```

### Modo de Desenvolvimento

Para habilitar auto-reload durante desenvolvimento:

```bash
streamlit run app.py --server.runOnSave true
```

### Configurar Tema

Crie o arquivo `.streamlit/config.toml`:

```toml
[theme]
primaryColor = "#FF4B4B"
backgroundColor = "#FFFFFF"
secondaryBackgroundColor = "#F0F2F6"
textColor = "#262730"
font = "sans serif"
```

## 🐛 Solução de Problemas

### ⚠️ BigQuery Desabilitado?

Se você vir "❌ BigQuery Desabilitado" na sidebar, verifique:

1. **Arquivo `.env` configurado?**
   ```bash
   BIGQUERY_CREDENTIALS_PATH=rj-nf-agent-tati.json
   ```

2. **Arquivo de credenciais existe?**
   ```bash
   ls -la rj-nf-agent-tati.json
   ```

3. **Reiniciou a aplicação?**
   - Pressione `Ctrl+C` no terminal
   - Execute novamente: `streamlit run app.py`

### 📖 Guia Completo de Troubleshooting

Para problemas mais específicos, consulte o **[Guia de Solução de Problemas](TROUBLESHOOTING.md)** que contém:

- ✅ Checklist de configuração
- 🔧 Soluções para erros comuns
- 📝 Como aumentar limites e timeouts
- 🐞 Debug e logs detalhados

## 📝 Exemplo de Uso

1. Abra o terminal e execute:
   ```bash
   streamlit run app.py
   ```

2. No navegador, faça upload de um PDF de prestação de contas

3. Clique em "🚀 Analisar PDF"

4. Aguarde a análise (pode levar alguns segundos)

5. Revise os resultados:
   - Dados extraídos pelo Gemini
   - Dados do BigQuery (se disponível)
   - Validações e classificação

6. Se desejar, baixe o relatório em Excel

## 🎯 Casos de Uso

- ✅ Análise rápida de uma nota fiscal específica
- ✅ Validação pontual antes de enviar para processamento em lote
- ✅ Exploração e teste de PDFs individuais
- ✅ Demonstração para stakeholders
- ✅ Treinamento de usuários

## 🔐 Segurança

- ⚠️ Não exponha esta aplicação publicamente sem autenticação
- ⚠️ PDFs enviados são processados em memória e não são salvos no servidor
- ✅ Credenciais são carregadas de variáveis de ambiente
- ✅ Comunicação com APIs externas via HTTPS

## 📞 Suporte

Para dúvidas ou problemas:
- Consulte o [README.md](README.md) principal
- Verifique as configurações em [config.py](config.py)
- Revise as variáveis de ambiente no `.env`
