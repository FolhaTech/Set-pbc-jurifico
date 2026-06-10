from core.enums import LadoProcesso


class ClassificadorPolo:
    def classificar(self, e_nosso: bool) -> LadoProcesso:
        return LadoProcesso.NOSSO_CLIENTE if e_nosso else LadoProcesso.OPERADORA
