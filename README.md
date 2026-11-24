# 🎬 PostOp

Plataforma para criar vídeos verticais (9:16) e postar no TikTok.

**Dois modos de geração**

1. **Cortes do YouTube**: cole um link. O PostOp baixa o vídeo, transcreve o áudio localmente (Whisper, grátis),
   a IA (OpenRouter) escolhe os melhores trechos e gera cortes 1080x1920 com legenda animada (palavra destacada),
   enquadramento automático no rosto ou fundo desfocado.
2. **Vídeo 3D por tema**: escolha um dos 14 temas prontos (Curiosidades, Terror, Mistérios, Lendas brasileiras,
   Mitologia, História em 1 minuto, Universo, Animais incríveis, E se...?, Ciência por dentro, Fábulas infantis,
   Motivação, Satisfatório, Humor absurdo) ou escreva uma ideia livre. **Só o roteiro usa IA**: o modelo de texto do
   OpenRouter recebe o catálogo do motor 3D do PostOp e descreve cada cena (cenário, horário, clima, câmera, quem
   aparece e o que faz). O servidor **monta e anima as cenas em 3D por código** (pessoas, animais, objetos, blocos,
   cenários), sem gerar imagem nem vídeo por IA, e junta tudo com transições, texto na tela e música opcional.
   Sem API key (ou se a IA falhar) o roteiro é montado automaticamente a partir da ideia.
   **Som**: narração com voz em português gerada no próprio servidor (Kokoro: Dora, Alex ou Santa), com a
   legenda acompanhando a fala palavra por palavra; efeitos sonoros e ambiente sintetizados por código e
   sincronizados com as cenas (passos, quedas, explosões, pássaros, chuva, ondas...); e música opcional, que
   abaixa sozinha quando a narração fala. Cada item liga e desliga no painel.
   Os temas ficam em `app/pipelines/themes.py` (fácil de criar novos).

Depois é só postar no TikTok (Content Posting API oficial): publicação direta ou envio para os rascunhos do app.

## Stack

- **API + painel**: FastAPI (Python 3.12), painel em JS puro servido pela própria API.
- **Worker**: processa a fila guardada no Postgres (sem Redis), um job por vez.
- **Banco**: Postgres 16 próprio da stack.
- **Mídia**: ffmpeg, yt-dlp (+ Deno), faster-whisper, OpenCV (detecção de rosto).
- **Motor 3D** (`app/render3d`): renderizador próprio em numpy + OpenCV, sem GPU. Cenas renderizadas em paralelo.
- **IA**: OpenRouter, só texto (escolher cortes e escrever roteiros). A API key é cadastrada na tela
  **Configurações** e fica criptografada.

## Modelos padrão (revisados em nov/2026)

| Uso | Modelo padrão | Custo aproximado |
|---|---|---|
| Escolher cortes / roteiro | `google/gemini-2.5-flash-lite` (reserva `openrouter/free`) | US$ 0,10 / 0,40 por milhão de tokens (centavos por vídeo); reserva grátis |
| Cenas 3D | motor próprio (`app/render3d`) | grátis |
| Narração | voz local Kokoro (baixa ~350 MB uma vez, em `DATA_DIR/models/kokoro`) | grátis |
| Efeitos sonoros e ambiente | sintetizados por código (`app/render3d/sound.py`) | grátis |
| Transcrição | Whisper local (`small`) | grátis |

- Sem créditos no OpenRouter, os modelos `:free` e o `openrouter/free` têm limite de 50 pedidos por dia
  (1.000 por dia depois de comprar US$ 10 em créditos).

Os modelos de texto podem ser trocados em **Configurações → IA (OpenRouter)**, que mostra os recomendados e tem um
botão para listar os modelos e preços atuais.

## Motor 3D

Cada cena do roteiro chega assim (a IA só pode usar nomes do catálogo, que vai no prompt dela):

```json
{"text": "Ela juntou blocos para subir alto",
 "scene3d": {"setting": "park", "time": "sunset", "weather": "none", "camera": "crane_up",
             "actors": [{"type": "turtle", "color": "#5cb85c", "actions": ["jump"]},
                        {"type": "block", "count": 10, "actions": ["stack"], "position": "right"}]}}
```

- **Catálogo**: ~45 tipos de pessoa (com roupas, chapéus e cabelos), ~25 animais, aves, peixes, criaturas e mais de
  130 objetos (blocos, lego, dominós, casas, prédios, castelo, carros, foguete, planetas, buraco negro, DNA, átomo...).
- **Ações**: andar, correr, pular, acenar, dançar, voar, nadar, sentar, dormir... para personagens; girar, quicar,
  cair do céu, crescer, explodir, abrir, decolar... para objetos; e ações de grupo (empilhar, construir, dominó,
  espalhar, chuva de objetos).
- **Cenários**: 29 lugares (floresta, cidade, praia, fundo do mar, espaço, quarto, palco...) com horário (dia,
  pôr do sol, amanhecer, noite), clima (chuva, neve, neblina, vaga-lumes, confete...) e 16 movimentos de câmera.
  O enquadramento é automático e a decoração nunca fica na frente da câmera.
- A IA pode escrever em português ou inglês: `app/render3d/spec.py` traduz sinônimos ("gato", "empilhar",
  "pôr do sol"), corrige valores fora da faixa e deduz a cena pelo texto quando faltar algo.

Para criar coisas novas: modelos em `app/render3d/models.py` (primitivas de `geom.py` montadas em nós com juntas),
ações em `actions.py`, cenários e estilos visuais em `world.py`, e sinônimos em `spec.py`. A variável
`RENDER_WORKERS` limita quantas cenas renderizam ao mesmo tempo (padrão: núcleos da máquina, até 4).

## Deploy (Portainer / Docker Swarm)

1. Aponte o DNS do domínio (ex.: `postop.seudominio.com`) para o servidor.
2. Portainer → **Stacks → Add stack** → cole `deploy/postop-stack.yml` (usa o Traefik que já existe na rede
   `network_public`) ou `deploy/postop-stack-standalone.yml` (traz o próprio Traefik, para servidor sem proxy).
3. Troque os campos marcados com `<<< TROQUE` e clique em **Deploy the stack**.
4. Acesse o domínio, entre com `ADMIN_USER` / `ADMIN_PASSWORD`, cadastre a API key do OpenRouter e siga o
   **Passo a passo TikTok** dentro da plataforma.

Se o pacote da imagem no GHCR estiver privado, cadastre o registry `ghcr.io` no Portainer
(usuário do GitHub + token com `read:packages`) ou deixe o pacote público em GitHub → Packages → postop → Settings.

### Variáveis de ambiente

| Variável | Descrição |
|---|---|
| `ADMIN_USER`, `ADMIN_PASSWORD` | Login da plataforma |
| `PUBLIC_URL` | URL pública, sem barra no final (usada no Redirect URI do TikTok) |
| `SECRET_KEY` | Chave da sessão e da criptografia das configurações. Não troque depois de usar |
| `DATABASE_URL` | `postgresql://usuario:senha@host:5432/banco` |
| `DATA_DIR` | Pasta dos vídeos/modelos (padrão `/data`) |
| `API_WORKERS` | Processos do uvicorn (padrão 2) |

## CI/CD (GitHub Actions)

A cada push na `main`:

1. **Lint e testes** (ruff + pytest com ffmpeg real).
2. **Versão**: calcula a próxima versão semver pelos commits desde a última tag
   (`feat:` → minor, `!:`/`BREAKING CHANGE` → major, resto → patch).
3. **Imagem Docker** (amd64 e arm64, ex.: VPS Oracle Ampere) publicada em `ghcr.io/dhqdev/postop` com as tags `latest`, `X.Y.Z`, `X.Y` e `sha-…`.
4. **Release** `vX.Y.Z` criada no GitHub com as notas automáticas.

Para atualizar no Portainer: abra a stack e clique em **Update the stack** com **Re-pull image** ligado
(ou fixe uma versão, ex.: `ghcr.io/dhqdev/postop:0.2.0`).

## Desenvolvimento

```bash
docker compose up --build        # http://localhost:8000  (admin / admin)
# ou
pip install -r requirements-dev.txt
uvicorn app.main:app --reload    # API
python -m app.worker             # worker (outro terminal)
pytest -q && ruff check .
```
