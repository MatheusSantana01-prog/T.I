"""Constantes do sistema (sem nada de Streamlit aqui)."""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ARQUIVO_DADOS = RAIZ / "estoque_ti.json"
ARQUIVO_USUARIOS = RAIZ / "usuarios_ti.json"
ARQUIVO_SESSOES = RAIZ / "sessoes_ti.json"
PASTA_BACKUP = RAIZ / "backups"
DIAS_BACKUP = 30

STATUS_OK = "✅ Disponível"
STATUS_ALERTA = "⚠️ Alerta (Reposição)"
STATUS_CRITICO = "🚨 Crítico (Zerado)"
COR_STATUS = {STATUS_OK: "#22c55e", STATUS_ALERTA: "#f59e0b", STATUS_CRITICO: "#ef4444"}

EM_ESTOQUE = "Em estoque"
SAIU = "Saiu"

CATEGORIAS_SUGERIDAS = [
    "Periféricos",
    "Cabos e Conectividade",
    "Armazenamento",
    "Redes",
    "Computadores",
]

PERFIL_ADMIN = "Administrador"
PERFIL_OPERADOR = "Operador"
PERFIL_LEITURA = "Somente leitura"
PERFIS = [PERFIL_ADMIN, PERFIL_OPERADOR, PERFIL_LEITURA]

MIN_SENHA = 8
MAX_TENTATIVAS = 5
BLOQUEIO_MINUTOS = 5
ITERACOES_HASH = 200_000
SESSAO_HORAS = 12
