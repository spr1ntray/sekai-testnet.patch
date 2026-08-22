# Sekai Testnet — пакет Soft Hub

Софт для тестнета Sekai / Hyperliquid. Ставится в Soft Hub как `.softhub.zip`.

Ключи, прокси и AdsPower берутся только из хранилища Hub. Своих файлов с секретами в пакете нет.

## Действия

- Полный цикл — кран в AdsPower, затем mint / redeem / swap / LP
- Только активности — ончейн без крана
- Только кран — QuickNode в окне профиля
- Парсинг — балансы, без транзакций

У каждого кошелька свой темп и набор действий.

## Сборка

Из корня Soft Hub:

```bash
python3 scripts/build_plugin.py ../sekai_testnet/sekai-testnet dist/sekai-testnet-1.0.0.softhub.zip
```
