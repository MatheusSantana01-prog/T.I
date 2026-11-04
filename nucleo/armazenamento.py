"""Leitura e gravação dos dados.

Hoje tudo fica em arquivos JSON. Para trocar por um banco de dados no futuro, basta
reescrever as funções deste arquivo (carregar_* / salvar_*), mantendo os mesmos
formatos de entrada e saída; o resto do sistema não precisa mudar.
"""
import io
import json
import os
import re
import shutil
import zipfile
from datetime import date, datetime, timedelta

from . import config
from .modelos import ItemTI


class ErroArquivo(Exception):
    """Arquivo de dados existe mas não pôde ser lido."""


# ---------------------------------------------------------------- utilidades
def escrever_json_atomico(caminho, dados):
    """Grava num arquivo temporário e troca de uma vez (evita arquivo pela metade)."""
    tmp = caminho.with_suffix(".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, caminho)


def _ler_json(caminho):
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        raise ErroArquivo(f"Não foi possível ler {caminho.name}: {e}") from e


# ---------------------------------------------------------------- backup
def backup_diario():
    """Copia os arquivos de dados uma vez por dia e apaga cópias com mais de 30 dias."""
    hoje = date.today().isoformat()
    try:
        config.PASTA_BACKUP.mkdir(exist_ok=True)
        for caminho in (config.ARQUIVO_DADOS, config.ARQUIVO_USUARIOS):
            if caminho.exists():
                destino = config.PASTA_BACKUP / f"{caminho.stem}_{hoje}{caminho.suffix}"
                if not destino.exists():
                    shutil.copy2(caminho, destino)
        limite = date.today() - timedelta(days=config.DIAS_BACKUP)
        for arq in config.PASTA_BACKUP.glob("*_????-??-??.json"):
            m = re.search(r"_(\d{4}-\d{2}-\d{2})\.json$", arq.name)
            if m and date.fromisoformat(m.group(1)) < limite:
                arq.unlink()
    except OSError:
        pass  # backup nunca deve impedir o uso do sistema


def listar_backups():
    if not config.PASTA_BACKUP.exists():
        return []
    return sorted((a.name for a in config.PASTA_BACKUP.glob("*.json")), reverse=True)


def gerar_zip_backup():
    """Zip em memória com os arquivos de dados atuais (para o admin baixar)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for caminho in (config.ARQUIVO_DADOS, config.ARQUIVO_USUARIOS):
            if caminho.exists():
                z.write(caminho, caminho.name)
    return buf.getvalue()


# ---------------------------------------------------------------- estoque
def dados_padrao():
    itens = [
        ItemTI("ADAPTADOR USB P/ TIPO C", "Periféricos", 2),
        ItemTI("CABO DE ENERGIA 20 A", "Periféricos", 5, 5),
        ItemTI("DESKTOPS", "Periféricos", 1),
        ItemTI("HDMI", "Cabos e Conectividade", 9),
    ]
    return {"Matriz": {"produtos": {i.nome: i for i in itens}, "historico": []}}


_PADRAO_LEGADO = re.compile(r"\s*\(\s*PELO MENOS\s+(\d+)\s*\)\s*$", re.IGNORECASE)


def limpar_nomes_legados(filiais):
    """'CABO X (PELO MENOS 5)' vira 'CABO X' com alerta a partir de 5."""
    for dados in filiais.values():
        for nome in list(dados["produtos"].keys()):
            m = _PADRAO_LEGADO.search(nome)
            if not m:
                continue
            novo = _PADRAO_LEGADO.sub("", nome).strip()
            if novo and novo not in dados["produtos"]:
                item = dados["produtos"].pop(nome)
                item.nome = novo
                item.estoque_minimo = int(m.group(1))
                dados["produtos"][novo] = item
    return filiais


def carregar_dados():
    """Devolve {filial: {"produtos": {nome: ItemTI}, "historico": [...]}}."""
    if not config.ARQUIVO_DADOS.exists():
        return dados_padrao()
    bruto = _ler_json(config.ARQUIVO_DADOS)
    try:
        if "filiais" in bruto:
            filiais = {}
            for f in bruto["filiais"]:
                itens = [ItemTI.from_dict(p) for p in f.get("produtos", [])]
                filiais[f["nome"]] = {
                    "produtos": {i.nome: i for i in itens},
                    "historico": f.get("historico", []),
                }
            if not filiais:
                return dados_padrao()
        elif "produtos" in bruto:  # formato antigo: vira a filial "Matriz"
            itens = [ItemTI.from_dict(p) for p in bruto.get("produtos", [])]
            filiais = {
                "Matriz": {
                    "produtos": {i.nome: i for i in itens},
                    "historico": bruto.get("historico", []),
                }
            }
        else:
            return dados_padrao()
    except (KeyError, TypeError, ValueError) as e:
        raise ErroArquivo(f"Formato inesperado em {config.ARQUIVO_DADOS.name}: {e}") from e
    return limpar_nomes_legados(filiais)


def salvar_dados(filiais):
    backup_diario()
    payload = {
        "filiais": [
            {
                "nome": nome,
                "produtos": [i.to_dict() for i in dados["produtos"].values()],
                "historico": dados["historico"],
            }
            for nome, dados in filiais.items()
        ]
    }
    escrever_json_atomico(config.ARQUIVO_DADOS, payload)


# ---------------------------------------------------------------- usuários e sessões
def carregar_usuarios():
    if config.ARQUIVO_USUARIOS.exists():
        return _ler_json(config.ARQUIVO_USUARIOS)
    return {}


def salvar_usuarios(usuarios):
    escrever_json_atomico(config.ARQUIVO_USUARIOS, usuarios)


def carregar_sessoes():
    if config.ARQUIVO_SESSOES.exists():
        try:
            return json.loads(config.ARQUIVO_SESSOES.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def salvar_sessoes(sessoes):
    escrever_json_atomico(config.ARQUIVO_SESSOES, sessoes)


def agora():
    return datetime.now()
