"""Telas de login e controle de sessão (com 'lembrar de mim' por cookie)."""
import streamlit as st
import streamlit.components.v1 as components

from nucleo import armazenamento, config, seguranca

COOKIE = "ti_sessao"


# ------------------------------------------------------------------ cookie de sessão
def _ler_cookie():
    try:
        return st.context.cookies.get(COOKIE)  # exige Streamlit 1.37 ou mais novo
    except Exception:  # noqa: BLE001
        return None


def _js_cookie(valor, segundos):
    """Grava (ou apaga, com segundos=0) o cookie no navegador."""
    components.html(
        f"""<script>
        (function () {{
          var seg = "";
          try {{ if (window.parent.location.protocol === "https:") seg = "; Secure"; }} catch (e) {{}}
          var c = "{COOKIE}={valor}; path=/; max-age={segundos}; SameSite=Strict" + seg;
          try {{ window.parent.document.cookie = c; }} catch (e) {{ document.cookie = c; }}
        }})();
        </script>""",
        height=0,
    )


def _iniciar_sessao(login):
    """Marca o usuário como logado e prepara o cookie para a próxima renderização."""
    st.session_state["usuario"] = login
    try:
        sessoes = armazenamento.carregar_sessoes()
        token = seguranca.criar_sessao(sessoes, login)
        armazenamento.salvar_sessoes(sessoes)
        st.session_state["_cookie_novo"] = token
    except OSError:
        pass  # sem cookie o login continua funcionando (só não sobrevive ao F5)


def aplicar_cookie_pendente():
    token = st.session_state.pop("_cookie_novo", None)
    if token:
        _js_cookie(token, config.SESSAO_HORAS * 3600)


def identificar_usuario(usuarios):
    """Devolve o login da sessão atual (ou restaurado pelo cookie); None se não logado."""
    atual = st.session_state.get("usuario")
    if atual in usuarios and usuarios[atual]["ativo"]:
        return atual
    st.session_state.pop("usuario", None)
    token = _ler_cookie()
    if token:
        login = seguranca.validar_sessao(token, usuarios, armazenamento.carregar_sessoes())
        if login:
            st.session_state["usuario"] = login
            return login
    return None


def sair():
    """Callback do botão Sair."""
    try:
        token = _ler_cookie()
        if token:
            sessoes = armazenamento.carregar_sessoes()
            seguranca.encerrar_sessao(token, sessoes)
            armazenamento.salvar_sessoes(sessoes)
    except OSError:
        pass
    st.session_state.clear()
    st.session_state["_apagar_cookie"] = True


# ------------------------------------------------------------------ telas
def tela_primeiro_acesso(usuarios):
    _, centro, _ = st.columns([1, 1.4, 1])
    with centro:
        st.markdown("<h1 style='color:#ffffff;'>📦 TI Stock PRO</h1>", unsafe_allow_html=True)
        st.subheader("Primeiro acesso: criar o administrador")
        st.caption("Este usuário terá acesso a todas as filiais e poderá criar os demais usuários.")
        with st.form("form_primeiro_acesso"):
            nome = st.text_input("Seu nome:")
            login = st.text_input("Usuário (login):", placeholder="ex: admin")
            senha = st.text_input(f"Senha (mínimo {config.MIN_SENHA} caracteres):", type="password")
            senha2 = st.text_input("Repita a senha:", type="password")
            criar = st.form_submit_button("Criar administrador")
        if criar:
            login = login.strip().lower()
            if not nome.strip():
                st.error("Informe o seu nome.")
            elif not seguranca.login_valido(login):
                st.error("Usuário: 3 a 30 caracteres, só letras minúsculas, números, ponto, _ ou -.")
            elif len(senha) < config.MIN_SENHA:
                st.error(f"A senha precisa ter pelo menos {config.MIN_SENHA} caracteres.")
            elif senha != senha2:
                st.error("As senhas não conferem.")
            else:
                usuarios[login] = seguranca.novo_usuario(nome, config.PERFIL_ADMIN, [], senha)
                armazenamento.salvar_usuarios(usuarios)
                _iniciar_sessao(login)
                st.rerun()


def tela_login(usuarios):
    if st.session_state.pop("_apagar_cookie", False):
        _js_cookie("", 0)
    _, centro, _ = st.columns([1, 1.2, 1])
    with centro:
        st.markdown("<h1 style='color:#ffffff;'>📦 TI Stock PRO</h1>", unsafe_allow_html=True)
        st.caption("Entre com seu usuário e senha.")
        with st.form("form_login"):
            login = st.text_input("Usuário:")
            senha = st.text_input("Senha:", type="password")
            entrar = st.form_submit_button("Entrar")
        if entrar:
            resultado, chave = seguranca.verificar_login(usuarios, login, senha)
            if chave in usuarios:
                armazenamento.salvar_usuarios(usuarios)  # grava contadores de tentativas
            if resultado == "ok":
                _iniciar_sessao(chave)
                st.rerun()
            elif resultado == "bloqueado":
                st.error("Muitas tentativas inválidas. Aguarde alguns minutos e tente de novo.")
            else:
                st.error("Usuário ou senha inválidos.")
