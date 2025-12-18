# Extrator de Informações de Notas Fiscais

Este projeto utiliza o Google Gemini para extrair informações de notas fiscais de arquivos PDF.

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

1. Coloque todos os arquivos PDF na pasta `files_pdfs/`

2. Execute o script:
```bash
python extrair_notas_fiscais.py
```

3. O script irá:
   - Processar cada PDF individualmente
   - Extrair informações de todas as notas fiscais encontradas
   - Gerar uma planilha Excel com os resultados

4. O arquivo Excel será gerado no mesmo diretório com o nome:
   `resultado_notas_fiscais_AAAAMMDD_HHMMSS.xlsx`

## Estrutura do Projeto

```
.
├── extrair_notas_fiscais.py  # Script principal
├── requirements.txt           # Dependências Python
├── .env.example              # Exemplo de configuração
├── .env                      # Suas configurações (não versionar)
├── files_pdfs/               # Pasta com os PDFs a processar
└── README.md                 # Este arquivo
```

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

O script pode consultar o BigQuery para enriquecer os dados extraídos com informações adicionais.

### Como Funciona

Para cada PDF processado, o script:
1. Extrai informações usando o Gemini
2. Consulta a tabela `despesas` no BigQuery usando o nome do arquivo
3. Adiciona à planilha Excel: `num_documento`, `valor_documento`, `valor_pago_total`

### Configuração

1. **Crie uma Service Account no Google Cloud**:
   - Acesse o [Console GCP](https://console.cloud.google.com/)
   - Vá em "IAM & Admin" > "Service Accounts"
   - Crie uma service account com permissão de leitura no BigQuery
   - Baixe o arquivo JSON de credenciais

2. **Configure o arquivo `.env`**:
```bash
BIGQUERY_ENABLED=true
BIGQUERY_PROJECT_ID=rj-cvl
BIGQUERY_DATASET=adm_contrato_gestao
BIGQUERY_TABLE=despesas
GOOGLE_APPLICATION_CREDENTIALS=/caminho/para/service-account.json
```

3. **Instale as dependências do BigQuery**:
```bash
pip install google-cloud-bigquery db-dtypes
```

### Colunas Adicionadas na Planilha

Quando o BigQuery está habilitado, as seguintes colunas são adicionadas:

- **Num Documento (BQ)**: Número do documento no BigQuery
- **Valor Documento (BQ)**: Valor do documento registrado no BigQuery
- **Valor Pago Total (BQ)**: Soma dos valores pagos

Se o arquivo não for encontrado no BigQuery, essas colunas mostrarão "N/A".

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
