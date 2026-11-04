"""Senhas, tentativas de login e sessões (sem nada de Streamlit aqui)."""
import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta

from . import config


def gerar_hash(senha, salt=None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac(
        "sha256", senha.encode("utf-8"), bytes.fromhex(salt), config.ITERACOES_HASH
    ).hex()
    return salt, h


def conferir_senha(senha, salt, hash_salvo):
    _, h = gerar_hash(senha, salt)
    return hmac.compare_digest(h, hash_salvo)


def login_valido(login):
    return re.fullmatch(r"[a-z0-9._-]{3,30}", login) is not None


def novo_usuario(nome, perfil, filiais_liberadas, senha):
    salt, h = gerar_hash(senha)
    return {
        "nome": nome.strip(),
        "perfil": perfil,
        "filiais": [] if perfil == config.PERFIL_ADMIN else list(filiais_liberadas),
        "ativo": True,
        "salt": salt,
        "hash": h,
        "falhas": 0,
        "bloqueado_ate": None,
    }


def verificar_login(usuarios, login, senha, agora=None):
    """Confere usuário e senha. Devolve (resultado, chave_do_usuario).

    resultado: "ok", "bloqueado" ou "invalido". Atualiza contadores de falha
    (quem chama precisa salvar os usuários depois).
    """
    agora = agora or datetime.now()
    chave = login.strip().lower()
    u = usuarios.get(chave)
    if u is None:
        gerar_hash(senha)  # mesmo tempo de resposta para usuário inexistente
        return "invalido", chave
    if u.get("bloqueado_ate") and datetime.fromisoformat(u["bloqueado_ate"]) > agora:
        return "bloqueado", chave
    if u["ativo"] and conferir_senha(senha, u["salt"], u["hash"]):
        u["falhas"] = 0
        u["bloqueado_ate"] = None
        return "ok", chave
    u["falhas"] = u.get("falhas", 0) + 1
    if u["falhas"] >= config.MAX_TENTATIVAS:
        u["falhas"] = 0
        u["bloqueado_ate"] = (agora + timedelta(minutes=config.BLOQUEIO_MINUTOS)).isoformat()
    return "invalido", chave


# ---------------------------------------------------------------- sessões persistentes
def _hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def criar_sessao(sessoes, login, agora=None):
    """Cria um token novo (devolvido a quem chamou; só o hash fica guardado)."""
    agora = agora or datetime.now()
    for k in [k for k, v in sessoes.items() if datetime.fromisoformat(v["expira"]) < agora]:
        del sessoes[k]
    token = secrets.token_urlsafe(32)
    sessoes[_hash_token(token)] = {
        "usuario": login,
        "expira": (agora + timedelta(hours=config.SESSAO_HORAS)).isoformat(),
    }
    return token


def validar_sessao(token, usuarios, sessoes, agora=None):
    """Devolve o login dono do token, ou None se inválido/expirado/usuário inativo."""
    if not token:
        return None
    agora = agora or datetime.now()
    s = sessoes.get(_hash_token(token))
    if not s or datetime.fromisoformat(s["expira"]) < agora:
        return None
    u = usuarios.get(s["usuario"])
    if not u or not u["ativo"]:
        return None
    return s["usuario"]


def encerrar_sessao(token, sessoes):
    if token:
        sessoes.pop(_hash_token(token), None)
