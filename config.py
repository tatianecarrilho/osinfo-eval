"""
Configurações do projeto de extração de notas fiscais.
"""

# ============================================================================
# CONFIGURAÇÕES DE PASTAS
# ============================================================================
PASTA_PDFS = "files/files_100_2"  # Pasta onde estão os PDFs a serem processados
PASTA_RESULTADOS = "results"       # Pasta onde será salvo o arquivo Excel

# ============================================================================
# CONFIGURAÇÕES DO GOOGLE GEMINI
# ============================================================================
# NOTA: A chave da API (GEMINI_API_KEY) deve estar no arquivo .env
# Modelo a ser usado (opções: gemini-1.5-flash, gemini-1.5-pro, etc.)
GEMINI_MODEL = "gemini-3-flash-preview"

# Controla a criatividade do modelo (0.0 a 1.0)
# Valores baixos (0.1): mais determinístico e preciso
# Valores altos (0.9): mais criativo e variado
GEMINI_TEMPERATURE = 0.1

# Configurações de geração do Gemini
GEMINI_TOP_P = 0.95           # Amostragem nucleus (0.0 a 1.0)
GEMINI_TOP_K = 64             # Top-k amostragem
GEMINI_MAX_OUTPUT_TOKENS = 8192  # Máximo de tokens na resposta

# ============================================================================
# CONFIGURAÇÕES DO BIGQUERY
# ============================================================================
# NOTA: O caminho do arquivo de credenciais deve estar no arquivo .env
# Habilita ou desabilita a integração com BigQuery
BIGQUERY_ENABLED = True
BIGQUERY_PROJECT_ID = "rj-nf-agent"
BIGQUERY_DATASET = "poc_osinfo_ia"
BIGQUERY_TABLE = "despesas_recorte"

# ============================================================================
# CONFIGURAÇÕES DE PROCESSAMENTO
# ============================================================================
LIMITE_TAMANHO_PDF_MB = 100        # Tamanho máximo do PDF em MB
TIMEOUT_API_SEGUNDOS = 120         # Timeout para chamadas à API do Gemini

# ============================================================================
# CONFIGURAÇÕES DE VALIDAÇÃO
# ============================================================================
TOLERANCIA_COMPARACAO_VALORES = 0.01  # Tolerância para comparação de valores monetários

# Tipos de documentos válidos para identificação de notas fiscais
TIPOS_DOCUMENTOS_VALIDOS = [
    'nota fiscal',
    'danfe',
    'fatura telefonia',
    'fatura concessionária',
    'fatura',
    'nf',
    'nfe',
    'nf-e'
]
