"""Temas prontos do modo Vídeo 3D.

Cada tema é um "card" no painel: ao clicar, o formulário é preenchido com uma ideia pronta,
o estilo visual, o número de cenas e o tempo por cena. No backend, o tema também muda o
roteiro: as regras do gênero (`guide`) entram no prompt do roteirista.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

STYLES = {
    "pixar3d": "3D animated movie style, Pixar-like, soft global illumination, subsurface scattering, "
    "expressive characters, octane render, cinematic depth of field",
    "realista3d": "photorealistic 3D CGI render, Unreal Engine 5, ray tracing, cinematic lighting, "
    "ultra detailed, volumetric light",
    "documental": "hyper detailed 3D documentary visualization, nature documentary look, natural light, "
    "macro detail, realistic textures, cinematic composition",
    "sombrio": "dark cinematic horror 3D render, low key lighting, thick fog, desaturated cold colors, "
    "eerie atmosphere, volumetric moonlight, film grain, unsettling composition",
    "fantasia": "epic fantasy 3D illustration, magical glowing particles, painterly volumetric light, "
    "mythical atmosphere, rich colors, highly detailed",
    "anime3d": "3D anime style, cel-shaded, vibrant colors, dynamic composition, studio quality render",
    "lowpoly": "low poly 3D isometric diorama, clean geometric shapes, soft pastel lighting, blender render",
    "clay": "claymation 3D style, plasticine textures, handcrafted miniature set, tilt-shift, soft light",
    "neon": "futuristic 3D render, cyberpunk neon lights, glossy reflections, dark atmosphere, octane render",
}

STYLE_NAMES = {
    "pixar3d": "Animação 3D",
    "realista3d": "Realista",
    "documental": "Documentário",
    "sombrio": "Sombrio",
    "fantasia": "Fantasia épica",
    "anime3d": "Anime 3D",
    "lowpoly": "Low poly",
    "clay": "Massinha",
    "neon": "Neon",
}


@dataclass(frozen=True)
class Theme:
    key: str
    name: str
    tagline: str
    icon: str  # nome do ícone SVG do painel
    style: str
    scenes: int
    seconds: float
    guide: str  # regras do gênero para o roteirista (vai no prompt do sistema)
    ideas: tuple[str, ...]
    hashtags: tuple[str, ...]
    words: int = 8  # máximo de palavras do texto na tela por cena


THEMES: tuple[Theme, ...] = (
    Theme(
        key="curiosidades",
        name="Curiosidades",
        tagline="Fatos que parecem mentira, mas são reais",
        icon="bulb",
        style="documental",
        scenes=6,
        seconds=4,
        words=12,
        guide=(
            "Formato 'Você sabia?'. Cena 1: gancho com uma pergunta ou afirmação surpreendente. "
            "Cada cena seguinte revela UM fato verdadeiro e amplamente documentado, do menos ao mais "
            "chocante. Última cena: o fato mais impressionante e um convite para seguir o perfil. "
            "Nunca invente fatos nem números."
        ),
        ideas=(
            "5 curiosidades sobre o oceano profundo que parecem mentira",
            "Curiosidades sobre o Egito Antigo que não ensinam na escola",
            "Objetos do dia a dia com uma origem totalmente inesperada",
            "Os recordes mundiais mais estranhos que já foram registrados",
            "Curiosidades sobre o Brasil que até brasileiro duvida",
        ),
        hashtags=("#curiosidades", "#voceSabia", "#fatos"),
    ),
    Theme(
        key="terror",
        name="Terror",
        tagline="Histórias para assistir com a luz acesa",
        icon="ghost",
        style="sombrio",
        scenes=7,
        seconds=3.5,
        words=10,
        guide=(
            "História curta de terror. Cena 1: gancho inquietante em uma frase. Construa tensão "
            "crescente com detalhes sensoriais, ambientes escuros e algo fora do lugar. Penúltima "
            "cena: a revelação. Última cena: uma reviravolta perturbadora que deixa a dúvida no ar. "
            "Medo pelo suspense e pelo clima, sem sangue nem violência explícita."
        ),
        ideas=(
            "O elevador de um prédio abandonado continua subindo sozinho toda noite às 3h",
            "Uma babá recebe mensagens de alguém que diz estar vendo ela pela janela",
            "Um caminhoneiro dá carona para uma mulher de branco numa estrada deserta",
            "A boneca comprada num brechó amanhece cada dia num cômodo diferente",
            "Amigos encontram uma fita VHS com a gravação do dia seguinte",
        ),
        hashtags=("#terror", "#historiasdeterror", "#medo"),
    ),
    Theme(
        key="misterios",
        name="Mistérios",
        tagline="Casos que ninguém conseguiu explicar",
        icon="search",
        style="realista3d",
        scenes=6,
        seconds=4,
        words=10,
        guide=(
            "Tom de documentário investigativo sobre um mistério real e conhecido. Cena 1: pergunta "
            "intrigante. Depois: o que aconteceu, as pistas e as teorias mais conhecidas. Diferencie "
            "fato de teoria ('uma teoria diz que...'). Última cena: a pergunta em aberto e um convite "
            "para comentar qual teoria a pessoa acredita."
        ),
        ideas=(
            "O mistério do Triângulo das Bermudas",
            "O sinal Wow!, a mensagem misteriosa captada do espaço em 1977",
            "O que aconteceu com a colônia perdida de Roanoke",
            "O Manuscrito Voynich, o livro que ninguém consegue ler",
            "As Linhas de Nazca, desenhos gigantes que só fazem sentido vistos do céu",
        ),
        hashtags=("#misterio", "#misterios", "#inexplicavel"),
    ),
    Theme(
        key="folclore",
        name="Lendas brasileiras",
        tagline="Saci, Curupira, Iara e companhia",
        icon="leaf",
        style="fantasia",
        scenes=6,
        seconds=4,
        guide=(
            "Reconte uma lenda do folclore brasileiro de forma cinematográfica, respeitando a versão "
            "tradicional. Apresente a criatura, o lugar onde ela aparece (mata, rio, sertão), uma "
            "história de encontro e o aviso ou a lição da lenda. Clima de mistério e encantamento."
        ),
        ideas=(
            "O Curupira despista caçadores na floresta com seus pés virados para trás",
            "O Boitatá, a serpente de fogo que protege os campos",
            "O canto da Iara atrai um pescador para o fundo do rio",
            "O Saci apronta dentro de um redemoinho no meio do sítio",
            "O Boto cor-de-rosa aparece numa festa junina à beira do rio",
        ),
        hashtags=("#folclore", "#lendasbrasileiras", "#folclorebrasileiro"),
    ),
    Theme(
        key="mitologia",
        name="Mitologia",
        tagline="Deuses, monstros e heróis lendários",
        icon="bolt",
        style="fantasia",
        scenes=7,
        seconds=3.5,
        guide=(
            "Conte um mito clássico (grego, nórdico, egípcio...) como um trailer épico: herói ou "
            "deus, conflito, clímax e consequência. Linguagem simples e empolgante, fiel ao mito."
        ),
        ideas=(
            "Prometeu rouba o fogo dos deuses e entrega aos humanos",
            "Thor enfrenta Jörmungandr, a serpente que abraça o mundo",
            "Teseu entra no labirinto para enfrentar o Minotauro",
            "Anúbis pesa o coração dos mortos contra uma pena",
            "Pandora abre a caixa que não devia ser aberta",
        ),
        hashtags=("#mitologia", "#mitologiagrega", "#lendas"),
    ),
    Theme(
        key="historia",
        name="História em 1 minuto",
        tagline="Momentos que mudaram o mundo",
        icon="hourglass",
        style="realista3d",
        scenes=6,
        seconds=4,
        words=10,
        guide=(
            "Narre um fato histórico real em ordem cronológica, com datas e nomes corretos. Cena 1: "
            "gancho mostrando o impacto do evento. Depois: contexto, o momento decisivo e as "
            "consequências. Última cena: por que isso importa até hoje."
        ),
        ideas=(
            "As últimas horas de Pompeia antes da erupção do Vesúvio",
            "O voo do 14-Bis de Santos Dumont em Paris, em 1906",
            "O naufrágio do Titanic, minuto a minuto",
            "A corrida espacial até o primeiro passo na Lua",
            "Como as pirâmides do Egito provavelmente foram construídas",
        ),
        hashtags=("#historia", "#fatoshistoricos", "#aprendanotiktok"),
    ),
    Theme(
        key="espaco",
        name="Universo",
        tagline="O cosmos em escala épica",
        icon="planet",
        style="realista3d",
        scenes=6,
        seconds=4,
        words=10,
        guide=(
            "Explique um fenômeno do espaço com sensação de escala e espanto. Use comparações do dia "
            "a dia para dar noção de tamanho e distância. Apenas fatos científicos corretos."
        ),
        ideas=(
            "Uma viagem da Terra até a borda do universo observável",
            "O que aconteceria se você caísse num buraco negro",
            "A maior estrela conhecida comparada com o Sol",
            "Como seria passar um dia em cada planeta do Sistema Solar",
            "Pousando em Titã, a lua de Saturno com rios de metano",
        ),
        hashtags=("#universo", "#espaco", "#astronomia"),
    ),
    Theme(
        key="animais",
        name="Animais incríveis",
        tagline="Habilidades que parecem ficção",
        icon="paw",
        style="documental",
        scenes=6,
        seconds=4,
        words=10,
        guide=(
            "Mostre animais reais com habilidades extraordinárias: cada cena um animal ou um detalhe "
            "impressionante. Fatos verificáveis, tom de admiração, final com o mais surpreendente."
        ),
        ideas=(
            "Os animais mais resistentes do planeta, do tardígrado à barata",
            "O polvo: três corações, sangue azul e um cérebro em cada braço",
            "Animais que brilham no escuro no fundo do mar",
            "Os caçadores mais rápidos da natureza",
            "A vida secreta de uma colônia de formigas",
        ),
        hashtags=("#animais", "#natureza", "#vidaselvagem"),
    ),
    Theme(
        key="e_se",
        name="E se...?",
        tagline="Hipóteses malucas, respostas de verdade",
        icon="question",
        style="realista3d",
        scenes=6,
        seconds=4,
        words=10,
        guide=(
            "Explore um cenário hipotético passo a passo com base em ciência real. Cena 1: a pergunta. "
            "Cenas seguintes: as consequências em ordem (primeiros segundos, dias, anos). Última cena: "
            "a conclusão mais surpreendente."
        ),
        ideas=(
            "E se a Lua desaparecesse de repente?",
            "E se a Terra parasse de girar por um segundo?",
            "E se os dinossauros nunca tivessem sido extintos?",
            "E se você caísse num túnel que atravessa a Terra?",
            "E se os humanos conseguissem hibernar como os ursos?",
        ),
        hashtags=("#ese", "#ciencia", "#curiosidades"),
    ),
    Theme(
        key="ciencia",
        name="Ciência por dentro",
        tagline="Como as coisas funcionam de verdade",
        icon="atom",
        style="realista3d",
        scenes=6,
        seconds=4,
        words=10,
        guide=(
            "Explique um processo científico como uma viagem visual por dentro dele (corpo humano, "
            "máquinas, natureza). Uma etapa por cena, em ordem, com linguagem simples e correta."
        ),
        ideas=(
            "O que acontece no seu corpo quando você toma um café",
            "A viagem de uma fatia de pizza pelo sistema digestivo",
            "Como o cérebro cria os sonhos enquanto você dorme",
            "Como uma vacina ensina o corpo a se defender",
            "O que acontece em um segundo quando um raio cai",
        ),
        hashtags=("#ciencia", "#corpohumano", "#aprendanotiktok"),
    ),
    Theme(
        key="fabula",
        name="Fábulas infantis",
        tagline="Historinhas fofas com uma moral",
        icon="star",
        style="pixar3d",
        scenes=6,
        seconds=4,
        guide=(
            "Fábula curta para crianças, com personagens animais fofos e carismáticos, linguagem "
            "simples, um conflito leve e final feliz. Última cena: a moral da história em uma frase. "
            "Nada assustador."
        ),
        ideas=(
            "A tartaruguinha que sonhava em voar",
            "O esquilo que não queria dividir as nozes",
            "O vagalume que tinha medo do escuro",
            "O dragãozinho que espirrava bolhas de sabão em vez de fogo",
            "O ursinho que aprendeu a esperar a sua vez",
        ),
        hashtags=("#historiainfantil", "#fabula", "#criancas"),
    ),
    Theme(
        key="motivacional",
        name="Motivação",
        tagline="Jornadas de superação que inspiram",
        icon="mountain",
        style="realista3d",
        scenes=6,
        seconds=3.5,
        guide=(
            "Vídeo motivacional com narrativa visual de superação: o personagem começa por baixo, "
            "enfrenta obstáculos e conquista. Textos curtos e fortes, como frases de impacto. Última "
            "cena: uma frase memorável."
        ),
        ideas=(
            "Um escalador chega ao topo da montanha durante a tempestade",
            "A atleta que treina sozinha de madrugada até o dia da final",
            "Uma semente que rompe o asfalto e vira uma árvore",
            "Ficar 1% melhor todo dia: a jornada de um ano",
            "Do quarto pequeno ao palco lotado",
        ),
        hashtags=("#motivacao", "#foco", "#disciplina"),
    ),
    Theme(
        key="satisfatorio",
        name="Satisfatório",
        tagline="Loops relaxantes e hipnóticos",
        icon="waves",
        style="clay",
        scenes=6,
        seconds=3,
        words=4,
        guide=(
            "Vídeo satisfatório e relaxante, sem narrativa: cada cena mostra um movimento suave e "
            "tátil (massinha sendo cortada, areia cinética, gotas, engrenagens se encaixando) em "
            "cores harmoniosas. Texto na tela mínimo: uma ou duas palavras, ou vazio."
        ),
        ideas=(
            "Massinha colorida sendo cortada em fatias perfeitas",
            "Bolinhas de gude descendo trilhos de madeira em espiral",
            "Areia cinética sendo moldada em formas geométricas",
            "Engrenagens douradas se encaixando perfeitamente",
            "Gotas de tinta formando flores dentro da água",
        ),
        hashtags=("#satisfatorio", "#satisfying", "#relaxante"),
    ),
    Theme(
        key="humor",
        name="Humor absurdo",
        tagline="Situações nonsense que viralizam",
        icon="smile",
        style="pixar3d",
        scenes=6,
        seconds=3.5,
        guide=(
            "Comédia curta e absurda: uma situação do cotidiano levada ao extremo, personagens "
            "carismáticos e uma piada final na última cena. Humor leve para todos os públicos."
        ),
        ideas=(
            "Um gato que é promovido a gerente do escritório",
            "Um pão de forma que sonha em ser croissant",
            "Um pombo fazendo entrevista de emprego",
            "A geladeira que julga suas escolhas de madrugada",
            "A capivara que virou influencer de bem-estar",
        ),
        hashtags=("#humor", "#comedia", "#absurdo"),
    ),
)

THEME_MAP = {t.key: t for t in THEMES}


def public_themes() -> list[dict]:
    """Temas para o painel (cards)."""
    return [asdict(t) | {"style_name": STYLE_NAMES.get(t.style, t.style)} for t in THEMES]


def public_styles() -> list[dict]:
    return [{"key": k, "name": STYLE_NAMES.get(k, k)} for k in STYLES]
