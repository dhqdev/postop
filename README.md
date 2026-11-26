<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/logo/postop-logo-dark.svg">
    <img src="docs/logo/postop-logo-light.svg" alt="PostOp" width="360">
  </picture>
</p>

Plataforma para criar vídeos verticais (9:16) e postar no TikTok.

**Três modos de geração**

1. **Cortes do YouTube**: cole um link e diga que parte do vídeo usar (o vídeo inteiro ou só um trecho, ex.:
   12:30 até 25:00). Só esse pedaço é baixado e transcrito (Whisper local, grátis). Depois escolha como cortar:
   - **A IA escolhe**: a IA recebe só o texto do trecho, em formato compacto, e devolve os melhores momentos;
   - **Eu digo os trechos**: um corte por linha (`1:20-2:05 Título`), sem IA;
   - **Dividir em partes**: o trecho vira Parte 1, Parte 2, Parte 3... do tamanho escolhido, com "PARTE N" escrito
     no vídeo, sem IA.

   Os cortes saem em 1080x1920 com legenda animada (palavra destacada) e enquadramento automático no rosto ou fundo
   desfocado.
2. **Animação 2D**: histórias animadas no estilo dos vídeos de curiosidades e de histórias bíblicas do TikTok
   (papel recortado ou vetor flat). A IA escreve o roteiro e o **motor 2D do PostOp desenha tudo por código**:
   personagens montados em partes (rosto com expressões, roupas, cabelo, acessórios), animais, cenários, objetos,
   faixas de título, balões, listas, contadores, efeitos e legenda palavra por palavra no próprio quadro.
3. **Vídeo 3D por tema**: o mesmo roteiro por tema, animado pelo motor 3D próprio (pessoas, animais, objetos,
   blocos e cenários).

Nos modos 2D e 3D há 15 temas prontos (Curiosidades, Terror, Mistérios, Lendas brasileiras, Mitologia, História em
1 minuto, Universo, Animais incríveis, E se...?, Ciência por dentro, Fábulas infantis, Motivação, Humor absurdo,
Histórias da Bíblia e Satisfatório, este só no 3D) ou ideia livre. **Só o roteiro usa IA**: uma chamada curta por
vídeo, com limite de tokens. Sem API key (ou se a IA falhar) o roteiro é montado automaticamente a partir da ideia.
**Som**: narração em português gerada no próprio servidor (Kokoro: Dora, Alex ou Santa), efeitos sonoros e
ambiente sintetizados por código e sincronizados com as ações, e música opcional que abaixa sozinha quando a
narração fala. Os temas ficam em `app/pipelines/themes.py` (fácil de criar novos).

Depois é só postar no TikTok (Content Posting API oficial): publicação direta ou envio para os rascunhos do app.

## Stack

- **API + painel**: FastAPI (Python 3.12), painel em JS puro servido pela própria API.
- **Worker**: processa a fila guardada no Postgres (sem Redis), um job por vez.
- **Banco**: Postgres 16 próprio da stack.
- **Mídia**: ffmpeg, yt-dlp (+ Deno), faster-whisper, OpenCV (detecção de rosto).
- **Motor 2D** (`app/render2d`): desenho vetorial com Pillow + composição com OpenCV, sem GPU.
- **Motor 3D** (`app/render3d`): renderizador próprio em numpy + OpenCV, sem GPU. Cenas renderizadas em paralelo.
- **IA**: OpenRouter, só texto (escolher cortes e escrever roteiros). A API key é cadastrada na tela
  **Configurações** e fica criptografada.

## Modelos padrão (revisados em nov/2026)

| Uso | Modelo padrão | Custo aproximado |
|---|---|---|
| Escolher cortes / roteiro | `google/gemini-2.5-flash-lite` (reserva `openrouter/free`) | US$ 0,10 / 0,40 por milhão de tokens (centavos por vídeo); reserva grátis |
| Cortes manuais e por partes | sem IA | grátis |
| Cenas 2D e 3D | motores próprios (`app/render2d`, `app/render3d`) | grátis |
| Narração | voz local Kokoro (baixa ~350 MB uma vez, em `DATA_DIR/models/kokoro`) | grátis |
| Efeitos sonoros e ambiente | sintetizados por código (`app/render3d/sound.py`) | grátis |
| Transcrição | Whisper local (`small`) | grátis |

- Sem créditos no OpenRouter, os modelos `:free` e o `openrouter/free` têm limite de 50 pedidos por dia
  (1.000 por dia depois de comprar US$ 10 em créditos).
- Economia de tokens: cada pedido tem `max_tokens`; a transcrição vai para a IA em blocos compactos com tempos
  inteiros; o catálogo do motor vai resumido; a resposta só é pedida de novo quando o JSON vem quebrado, e erro da
  API passa direto para o modelo reserva.

Os modelos de texto podem ser trocados em **Configurações → IA (OpenRouter)**, que mostra os recomendados e tem um
botão para listar os modelos e preços atuais.

## Motor 2D

Cada cena do roteiro chega assim (a IA só pode usar nomes do catálogo 2D, que vai resumido no prompt):

```json
{"narration": "O rei mandou todos se curvarem diante da estátua de ouro.",
 "place": "ancient_city", "time": "day", "banner": "A ESTÁTUA",
 "show": [{"id": "rei", "do": ["point"], "at": "left", "label": true},
          {"prop": "statue", "at": "right", "do": ["glow"]},
          {"type": "person", "count": 5, "do": ["bow"]}], "fx": "sparkles"}
```

- **Personagens**: cerca de 60 tipos de pessoa (rei, profeta, anjo, cientista, policial, astronauta, saci...) com
  10 expressões, e mais de 50 animais e criaturas. O elenco é fixo durante o vídeo: o mesmo personagem tem a mesma roupa e
  cor em todas as cenas.
- **Ações sem looping**: cada ação dura o tempo natural dela (um pulo, um aceno, uma reverência) e o personagem
  termina parado, olhando para a câmera ou para quem está falando. Andar e correr chegam ao lugar marcado.
- **Cenários**: 34 lugares com horário, mais de 130 objetos, faixa de título, cartão, etiqueta, figurinha, balão de
  fala, lista com checks, número/contador, gráfico e efeitos (corações, estrelas, fogo, neve, confete...).
- **Câmera e ritmo**: zoom, panorâmica, "soco" de zoom e tremida; cortes secos entre cenas, como nos vídeos de
  referência; cada cena dura o tempo da narração.
- Arquivos: desenho em `draw.py`, personagens em `characters.py`, animação em `anim.py`, objetos em `props.py`,
  cenários em `places.py`, sobreposições e legenda em `overlays.py`, cena em `scene.py` e leitura do roteiro em
  `story.py` (traduz sinônimos em português e corrige o que vier fora do catálogo).

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

Cada ação 3D também dura o tempo natural dela (sem repetir em looping): quem anda ou voa chega ao lugar marcado,
vira para a câmera e fica parado no enquadramento.

Para criar coisas novas: modelos em `app/render3d/models.py` (primitivas de `geom.py` montadas em nós com juntas),
ações em `actions.py`, cenários e estilos visuais em `world.py`, e sinônimos em `spec.py`. A variável
`RENDER_WORKERS` limita quantas cenas renderizam ao mesmo tempo (padrão: núcleos da máquina, até 4).

## TikTok

A integração segue a documentação oficial da Content Posting API (revisada em nov/2026):

- Login com OAuth v2 (`user.info.basic`, `video.publish`, `video.upload`), renovação automática do token (o
  refresh token mais recente é sempre guardado) e desconexão que também revoga o acesso no TikTok.
- Antes de cada post o PostOp consulta o perfil do criador (`creator_info`): privacidades permitidas, interações
  desligadas na conta e a duração máxima de vídeo.
- A tela de postar segue as regras de UX do TikTok: mostra a conta, a privacidade não vem escolhida, comentários,
  dueto e costura começam desmarcados, há a divulgação de conteúdo comercial (Sua marca / Conteúdo de marca, que não
  pode ser "Só eu") e o aviso de consentimento da Confirmação de Uso de Música. Vídeos 2D e 3D vão com o selo de
  conteúdo gerado por IA.
- Upload em partes com nova tentativa, título cortado em 2.200 caracteres (contagem UTF-16, como o TikTok) e erros
  explicados em português.
- **App ainda não aprovado (sem auditoria)**: os posts só saem como "Só eu" e a conta do TikTok precisa estar
  privada na hora de postar; até 5 contas por dia. Cada conta faz cerca de 15 posts por dia pela API, e o modo
  rascunho aceita até 5 envios pendentes.

A logo para o app no TikTok for Developers está em `docs/logo/postop-icon-1024.png`.

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
