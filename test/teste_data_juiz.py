import sys
sys.path.insert(0, ".")

from datetime import date
from core.services.calcular_prazo import CalcularPrazo

calc = CalcularPrazo()

data_juiz = date(2026, 7, 15)
resultado = calc.calcular_prazo_solicitado_juiz(data_juiz)

print("=== TESTE: Data do juiz ===")
print(f"Data que o juiz pediu : {data_juiz.strftime('%d/%m/%Y')}")
print(f"Data de agendamento   : {resultado.data_agendamento.strftime('%d/%m/%Y')}")
print(f"Data limite           : {resultado.data_limite.strftime('%d/%m/%Y')}")
print(f"Status temporal       : {resultado.status_temporal.value}")
print(f"Dias restantes        : {resultado.dias_restantes}")
print()

expected = date(2026, 7, 10)
assert resultado.data_agendamento == expected, (
    f"ERRO! Esperado {expected}, obtido {resultado.data_agendamento}"
)
print("✅ TESTE PASSOU: Agendamento = 10/07/2026 (15/07 - 5 dias)")