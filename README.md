# Extrator de Informações de Notas Fiscais

Este projeto utiliza o Google Gemini para extrair informações de notas fiscais de arquivos PDF.

## 🎯 Dois Modos de Uso

### 1. 🌐 Interface Web (Análise Individual)
Interface interativa com Streamlit para análise de PDFs individuais.
- Upload de um PDF por vez
- Visualização em tempo real dos resultados
- Ideal para análises pontuais e exploratórias

📖 **[Leia a documentação completa da aplicação web](APP_README.md)**

**Como executar:**
```bash
streamlit run app.py
```

### 2. 📦 Script em Lote (Processamento em Massa)
Script de linha de comando para processar múltiplos PDFs de uma vez.
- Processa todos os PDFs de uma pasta
- Gera arquivo Excel consolidado
- Ideal para processamento em massa

## Informações Extraídas

Para cada nota fiscal encontrada nos PDFs, o sistema extrai:

- Nome do arquivo
- Número total de páginas do PDF
- Número da página onde se encontra a nota fiscal
- CNPJ do prestador de serviço
- Tipo de documento (Nota Fiscal, DANFE, Fatura de Telefonia, Fatura de Concessionária, etc.)
- Número da NF
- Valor total da NF

## Tipos de Documentos Reconhecidos

O sistema reconhece os seguintes tipos de documentos como nota fiscal:

- Nota Fiscal (qualquer tipo)
- DANFE (Documento Auxiliar da Nota Fiscal Eletrônica)
- Faturas de telefonia
- Faturas de concessionárias (Light, CEG, Rioáguas, etc.)

## Pré-requisitos

- Python 3.8 ou superior
- Chave de API do Google Gemini

## Instalação

1. Clone ou baixe este repositório

2. Instale as dependências:
```bash
pip install -r requirements.txt
```

3. Configure suas credenciais:
   - Copie o arquivo `.env.example` para `.env`
   - Edite o arquivo `.env` e adicione sua chave de API do Gemini:

```bash
cp .env.example .env
```

Edite o arquivo `.env`:
```
GEMINI_API_KEY=sua_chave_api_aqui
GEMINI_MODEL=gemini-1.5-flash
GEMINI_TEMPERATURE=0.1
```

## Como Usar

1. Coloque todos os arquivos PDF na pasta configurada (padrão: `files/files_100_2/`)

2. Execute o script:
```bash
python extrair_notas_fiscais.py
```

3. O script irá:
   - Processar cada PDF individualmente
   - Extrair informações de todas as notas fiscais encontradas
   - Gerar uma planilha Excel com os resultados

4. O arquivo Excel será gerado na pasta `results/` com o nome:
   `resultado_notas_fiscais_AAAAMMDD_HHMMSS.xlsx`

## Estrutura do Projeto

```
.
├── app.py                     # 🌐 Aplicação web Streamlit (análise individual)
├── extrair_notas_fiscais.py  # 📦 Script em lote (processamento em massa)
├── config.py                  # Arquivo de configuração
├── requirements.txt           # Dependências Python
├── .env.example              # Exemplo de configuração
├── .env                      # Suas configurações (não versionar)
├── APP_README.md             # Documentação da aplicação web
├── README.md                 # Este arquivo
├── files/                    # Pasta com subpastas de PDFs
│   ├── files_10/            # PDFs para teste (10 arquivos)
│   ├── files_100/           # PDFs conjunto 1 (100 arquivos)
│   ├── files_100_2/         # PDFs conjunto 2 (100 arquivos) - PADRÃO
│   └── files_pdfs/          # PDFs diversos
└── results/                  # Pasta onde são salvos os arquivos Excel
```

## Configuração

O projeto separa configurações em dois arquivos seguindo melhores práticas de segurança:

### 1. Arquivo `.env` - Credenciais (NUNCA versionar)

Contém **apenas informações sensíveis**:
- `GEMINI_API_KEY` - Chave da API do Gemini (OBRIGATÓRIO)
- `BIGQUERY_CREDENTIALS_PATH` - Caminho do arquivo de credenciais (OBRIGATÓRIO se BigQuery habilitado)

**Configuração mínima do `.env`:**
```bash
GEMINI_API_KEY=sua_chave_api_aqui
BIGQUERY_CREDENTIALS_PATH=rj-nf-agent-tati.json
```

**Opcionalmente**, você pode sobrescrever valores do `config.py` no `.env`:
```bash
# Sobrescrever configurações (opcional)
GEMINI_MODEL=gemini-1.5-pro
GEMINI_TEMPERATURE=0.2
BIGQUERY_ENABLED=false
```

### 2. Arquivo `config.py` - Configurações do Projeto (versionado)

O arquivo [`config.py`](config.py) contém todas as configurações do projeto:

#### 📁 Pastas
```python
PASTA_PDFS = "files/files_100_2"  # Onde estão os PDFs
PASTA_RESULTADOS = "results"       # Onde salvar os resultados
```

#### 🤖 Google Gemini
```python
GEMINI_MODEL = "gemini-1.5-flash"      # Modelo (flash/pro)
GEMINI_TEMPERATURE = 0.1                # Criatividade (0.0-1.0)
GEMINI_TOP_P = 0.95                     # Amostragem nucleus
GEMINI_TOP_K = 64                       # Top-k
GEMINI_MAX_OUTPUT_TOKENS = 8192         # Tokens máximos
```

#### 📊 BigQuery
```python
BIGQUERY_ENABLED = True                 # Habilitar/desabilitar
BIGQUERY_PROJECT_ID = "rj-nf-agent"    # ID do projeto
BIGQUERY_DATASET = "poc_osinfo_ia"     # Dataset
BIGQUERY_TABLE = "despesas_recorte"    # Tabela/View
```

#### ⚙️ Processamento
```python
LIMITE_TAMANHO_PDF_MB = 100            # Tamanho máximo PDF
TIMEOUT_API_SEGUNDOS = 120             # Timeout API Gemini
```

#### ✅ Validação
```python
TOLERANCIA_COMPARACAO_VALORES = 0.01   # Tolerância valores
TIPOS_DOCUMENTOS_VALIDOS = [...]       # Tipos aceitos
```

### Hierarquia de Configuração

📌 **Regra simples:**
- **Credenciais** → Sempre no `.env` (obrigatório)
- **Configurações do projeto** → No `config.py` (pode ser sobrescrito pelo `.env`)

**Ordem de prioridade:**
1. **.env** - Maior prioridade (se a variável existir)
2. **config.py** - Valor padrão (se não houver no .env)

**Como usar:**
- **Alterar pasta de PDFs, modelo do Gemini, etc.** → Edite [`config.py`](config.py)
- **Adicionar credenciais, sobrescrever valores pontualmente** → Edite `.env`

## Observações

- O script processa um PDF por vez, enviando-o para o Gemini
- Se um PDF contiver múltiplas notas fiscais, todas serão extraídas
- Se não for encontrada nenhuma nota fiscal, será registrado "nota fiscal não encontrada"
- O tempo de processamento depende do número e tamanho dos PDFs

## Configuração do Gemini

Você pode ajustar as configurações do modelo no arquivo `.env`:

- `GEMINI_MODEL`: Modelo a ser usado (padrão: `gemini-1.5-flash`)
  - Opções: `gemini-1.5-flash`, `gemini-1.5-pro`, etc.
- `GEMINI_TEMPERATURE`: Controla a criatividade (0.0 a 1.0)
  - Valores baixos (0.1): mais determinístico e preciso
  - Valores altos (0.9): mais criativo e variado

## Integração com BigQuery (Opcional)

O script pode consultar o BigQuery para enriquecer os dados extraídos com informações adicionais e realizar validações automáticas.

### Como Funciona

Para cada PDF processado, o script:
1. Extrai informações usando o Gemini
2. Consulta a tabela de despesas no BigQuery usando o nome do arquivo
3. Adiciona dados do BigQuery: `num_documento`, `valor_documento`, `valor_pago_total`
4. Realiza validações automáticas comparando dados extraídos com dados do BigQuery
5. Classifica o documento como "Descartado", "Suspeito" ou "Não foi possível analisar"

### Configuração

1. **Coloque o arquivo de credenciais na raiz do projeto**:
   - Obtenha o arquivo JSON de service account com permissão de leitura no BigQuery
   - Salve o arquivo como `rj-nf-agent-tati.json` na raiz do projeto
   - O arquivo já está configurado no `.gitignore` para não ser versionado

2. **Configure o arquivo `.env`** (opcional - o código já tem valores padrão):
```bash
BIGQUERY_ENABLED=true
BIGQUERY_PROJECT_ID=rj-nf-agent
BIGQUERY_DATASET=poc_osinfo_ia
BIGQUERY_TABLE=despesas_recorte
BIGQUERY_CREDENTIALS_PATH=rj-nf-agent-tati.json
```

3. **Instale as dependências do BigQuery**:
```bash
pip install google-cloud-bigquery db-dtypes
```

### Validações Automáticas

O sistema realiza as seguintes validações:

1. **PDF possui NF em Despesas?**: Verifica se o número da NF extraído do PDF existe no BigQuery
2. **Valor Pago ≤ Valor Declarado?**: Verifica se o valor pago é menor ou igual ao valor do documento
3. **Valor NF == Valor Declarado?**: Verifica se o valor extraído do PDF é igual ao valor no BigQuery (tolerância de R$ 0,01)

### Classificação Final

Baseado nas validações, cada documento recebe uma classificação:

- **Descartado**: Todas as validações retornaram "SIM" - documento está OK
- **Suspeito**: Pelo menos uma validação retornou "NÃO" - requer revisão manual
- **Não foi possível analisar**: Documento não contém NF válida ou houve erro no processamento

### Colunas Adicionadas na Planilha

Quando o BigQuery está habilitado, as seguintes colunas são adicionadas:

- **Num Documento (BQ)**: Número do documento no BigQuery
- **Valor Documento (BQ)**: Valor do documento registrado no BigQuery (R$)
- **Valor Pago Total (BQ)**: Soma dos valores pagos (R$)
- **PDF possui NF em Despesas?**: SIM/NÃO/N/A
- **Valor Pago ≤ Valor Declarado?**: SIM/NÃO/N/A
- **Valor NF == Valor Declarado?**: SIM/NÃO/N/A
- **Classificação Final**: Descartado/Suspeito/Não foi possível analisar

Se o arquivo não for encontrado no BigQuery, as colunas mostrarão "N/A" e a classificação será "Suspeito".

## Solução de Problemas

### Erro: "GEMINI_API_KEY não encontrada"
- Verifique se você criou o arquivo `.env`
- Verifique se adicionou sua chave de API corretamente

### Erro ao processar PDF
- Verifique se o arquivo PDF não está corrompido
- Verifique se o arquivo não está protegido por senha

### Planilha não foi gerada
- Verifique se você tem permissão de escrita no diretório
- Verifique se há espaço em disco disponível

## Licença

Este projeto é de código aberto e está disponível para uso livre.
