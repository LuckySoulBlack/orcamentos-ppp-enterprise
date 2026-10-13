from datetime import datetime


_usuario_atual = {}


def set_usuario(usuario):
    global _usuario_atual
    _usuario_atual = dict(usuario or {})


def get_usuario():
    return dict(_usuario_atual)


def nome_usuario(padrao="usuário"):
    nome = str(_usuario_atual.get("nome") or _usuario_atual.get("usuario") or "").strip()
    return nome or padrao


def saudacao_atual():
    hora = datetime.now().hour
    if hora < 12:
        return "Bom dia"
    if hora < 18:
        return "Boa tarde"
    return "Boa noite"
