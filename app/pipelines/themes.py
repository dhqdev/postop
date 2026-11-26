"""Temas prontos do modo Vídeo 3D.

Cada tema é um "card" no painel: ao clicar, o formulário é preenchido com uma ideia pronta,
o estilo visual, o número de cenas e o tempo por cena. No backend, o tema também muda o
roteiro: as regras do gênero (`guide`) entram no prompt do roteirista, e `world`/`actor`
dizem ao motor 3D qual cenário e protagonista usar quando a IA não disser.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace

# Estilo visual do motor 3D (cores, luz, névoa, brilho). A descrição vai para o roteirista.
STYLES = {
    "pixar3d": "animação 3D colorida e fofa, luz suave e brilho nos contornos",
    "realista3d": "3D sóbrio, contraste e sombras marcadas",
    "documental": "tons naturais de documentário",
    "sombrio": "noite, névoa, cores frias, câmera tremida e clima de terror",
    "fantasia": "mágico, brilhos no ar e cores ricas",
    "anime3d": "cores vivas e sombreamento em faixas, como anime",
    "lowpoly": "low poly em tons pastel",
    "clay": "massinha, tons pastel e textura granulada",
    "neon": "noite com luzes neon e brilho intenso",
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

# Estilos da animação 2D (motor `app/render2d`)
STYLES2D = {
    "papel": "recorte de papel com textura e sombra suave",
    "flat": "vetor flat, cores chapadas e limpas",
}
STYLE2D_NAMES = {"papel": "Recorte de papel", "flat": "Vetor flat"}


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
    world: str = "studio"  # cenário 3D padrão do gênero
    actor: str = "person"  # protagonista padrão (quando a IA não disser)
    modes: tuple[str, ...] = ("3d", "2d")  # em quais modos o tema aparece
    place2d: str = "plain"  # cenário padrão da animação 2D
    actor2d: str = "person"  # protagonista padrão da animação 2D
    banner2d: int = 0  # cor da faixa de título (índice da paleta do motor 2D)


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
        world="studio",
        actor="scientist",
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
        world="graveyard",
        actor="ghost",
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
        world="forest",
        actor="explorer",
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
        world="jungle",
        actor="saci",
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
        world="temple",
        actor="knight",
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
        world="village",
        actor="person",
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
        world="space",
        actor="astronaut",
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
        world="forest",
        actor="fox",
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
        world="space",
        actor="earth",
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
        world="lab",
        actor="scientist",
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
        world="forest",
        actor="turtle",
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
        world="mountains",
        actor="athlete",
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
            "hipnótico com objetos (blocos se empilhando, dominós caindo em fila, bolinhas quicando, "
            "engrenagens girando, cubos montando formas) em cores harmoniosas. Texto na tela mínimo: "
            "uma ou duas palavras, ou vazio."
        ),
        ideas=(
            "Blocos coloridos caindo um a um até formar uma torre perfeita",
            "Uma fila enorme de dominós caindo em sequência",
            "Bolinhas de gude quicando em ritmo hipnótico",
            "Engrenagens douradas girando juntas sem parar",
            "Cubos que se montam sozinhos numa pirâmide e depois explodem",
        ),
        hashtags=("#satisfatorio", "#satisfying", "#relaxante"),
        world="studio",
        actor="block",
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
        world="city",
        actor="cat",
    ),
)

THEMES = THEMES + (
    Theme(
        key="biblia",
        name="Histórias da Bíblia",
        tagline="Passagens bíblicas contadas com carinho",
        icon="book",
        style="fantasia",
        scenes=7,
        seconds=4,
        words=10,
        guide=(
            "Reconte uma passagem da Bíblia fiel ao texto, respeitosa e fácil de entender para a família toda. "
            "Cena 1: gancho com o momento mais marcante. Depois: quem são os personagens, o conflito e como a "
            "história se resolve. Última cena: a lição da passagem em uma frase. Ponha a referência (livro, "
            "capítulo e versículos, ex.: 'Dn 3,16-18') no campo tag. Não invente fatos que não estão no texto."
        ),
        ideas=(
            "Os três jovens na fornalha ardente (Daniel 3)",
            "Davi enfrenta o gigante Golias",
            "Jonas é engolido por um grande peixe",
            "Noé constrói a arca antes do dilúvio",
            "O nascimento de Jesus em Belém",
        ),
        hashtags=("#biblia", "#historiasbiblicas", "#fe"),
        world="desert",
        actor="king",
    ),
)

# padrões da animação 2D por tema (cenário, protagonista, cor da faixa) e temas só de um modo
_THEME_2D = {
    "curiosidades": ("plain", "teacher", 0), "terror": ("graveyard", "ghost", 2), "misterios": ("night_city", "detective", 1),
    "folclore": ("jungle", "saci", 3), "mitologia": ("temple", "knight", 4), "historia": ("ancient_city", "explorer", 4),
    "espaco": ("space", "astronaut", 1), "animais": ("forest", "fox", 3), "e_se": ("plain", "person", 1),
    "ciencia": ("lab", "scientist", 3), "fabula": ("forest", "turtle", 0), "motivacional": ("city", "athlete", 0),
    "humor": ("office", "cat", 4), "biblia": ("ancient_city", "prophet", 0),
}  # fmt: skip
THEMES = tuple(
    replace(t, place2d=_THEME_2D[t.key][0], actor2d=_THEME_2D[t.key][1], banner2d=_THEME_2D[t.key][2])
    if t.key in _THEME_2D
    else replace(t, modes=("3d",))
    for t in THEMES
)
THEME_MAP = {t.key: t for t in THEMES}


def public_themes() -> list[dict]:
    """Temas para o painel (cards)."""
    return [asdict(t) | {"style_name": STYLE_NAMES.get(t.style, t.style)} for t in THEMES]


def public_styles() -> list[dict]:
    return [{"key": k, "name": STYLE_NAMES.get(k, k)} for k in STYLES]


def public_styles2d() -> list[dict]:
    return [{"key": k, "name": STYLE2D_NAMES.get(k, k)} for k in STYLES2D]
