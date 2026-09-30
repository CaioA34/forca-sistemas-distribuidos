# TASK-001-qa — correções apontadas pelo QA

1. `servidor.py`: após uma pausa longa (nó primário sem reserva por >= NAME_HOLD s), a primeira jogada
   depois da retomada libera jogadores que estavam consultando o tempo todo (`seen` só é atualizado quando
   o nó atende). Esperado: ao voltar a atender (novo reserva aceito em `attend`), ninguém é tratado como
   inativo por causa do tempo em que o nó esteve pausado. Cobrir com teste.
2. `gateway.py`: o Handler não tem timeout de socket; 128 conexões ociosas ocupam todos os `slots` e o
   gateway passa a fechar toda requisição legítima sem resposta. Esperado: conexão que não envia a
   requisição completa em tempo curto é encerrada e libera o slot. Cobrir com teste.
3. `forca/lobby.py`/`web/app.js`: reenvio de `SAIR` já aplicado devolve SEM_SALA (sem recibo, pois o
   jogador foi coletado). Hoje o navegador trata SEM_SALA como sucesso; documentar ou cobrir com teste.
4. Testes ausentes: colisão de `join` simultâneo entre dois nós; pausa longa + retomada; duplicata
   atrasada aplicada após comando seguinte.
