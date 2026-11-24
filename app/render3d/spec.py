"""Especificação da cena 3D: normaliza o que a IA escreveu, catálogo para o prompt e diretor sem IA.

A IA de texto recebe o catálogo (só nomes que o motor sabe desenhar) e devolve, por cena,
um objeto `scene3d`. Aqui tudo é conferido: nomes em português ou inglês viram os nomes
internos, valores fora da faixa são corrigidos e, se faltar algo, a cena é deduzida do texto.
"""

from __future__ import annotations

import re
import unicodedata

from . import models as M
from .actions import ACTIONS
from .geom import hex_rgb
from .scene import ActorSpec, SceneSpec
from .world import SETTINGS, TIMES


def plain(text: str) -> str:
    """Minúsculas, sem acentos e só letras/números separados por espaço."""
    t = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def _index(table: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for canon, words in table.items():
        out[plain(canon.replace("_", " "))] = canon
        for w in words.split(","):
            w = plain(w)
            if w:
                out.setdefault(w, canon)
    return out


TYPE_WORDS = {
    # pessoas
    "person": "pessoa,humano,human,gente,personagem,character,individuo,people,pessoas",
    "man": "homem,rapaz,moco,pai,father,dad,tio,guy,cara,prometeu,marido,namorado,irmao",
    "woman": "mulher,moca,mae,mother,mom,tia,lady,baba,pandora,esposa,namorada,irma,senhora",
    "child": "crianca,criancas,kid,kids,filho,filha,neto,neta",
    "boy": "menino,garoto,boy",
    "girl": "menina,garota,girl",
    "baby": "bebe,baby,nene,recem nascido",
    "old_man": "idoso,velho,avo,vovo,grandpa,old man,velhinho,anciao",
    "old_woman": "idosa,velha,vovozinha,grandma,old woman,velhinha",
    "astronaut": "astronauta,cosmonauta,astronaut",
    "robot": "robo,robot,androide,android,ciborgue,cyborg,maquina inteligente",
    "alien": "alien,alienigena,et,extraterrestre,marciano",
    "ghost": "fantasma,espirito,assombracao,alma penada,ghost,spirit,aparicao",
    "wizard": "mago,feiticeiro,bruxo,merlin,wizard,sorcerer,mage,gandalf",
    "witch": "bruxa,feiticeira,witch,cuca,medusa",
    "knight": "cavaleiro,guerreiro,guerreira,knight,warrior,heroi,hero,teseu,perseu,hercules,thor,gladiador,soldado,soldier,viking,espartano",
    "king": "rei,imperador,farao,king,emperor,pharaoh,zeus,odin,poseidon,hades,deus,god,sultao",
    "queen": "rainha,imperatriz,queen,cleopatra,deusa,goddess,atena,afrodite",
    "princess": "princesa,princess,fada,fairy",
    "scientist": "cientista,professor,professora,inventor,pesquisador,scientist,einstein,tesla,sabio",
    "doctor": "medico,medica,doutor,doctor,dentista,cirurgiao",
    "chef": "chef,cozinheiro,cozinheira,cook,padeiro,baker",
    "farmer": "fazendeiro,agricultor,caipira,campones,farmer,peasant,sitiante,jardineiro",
    "explorer": "explorador,aventureiro,cacador,hunter,arqueologo,archaeologist,turista,viajante,mochileiro",
    "cowboy": "cowboy,vaqueiro,peao,boiadeiro",
    "worker": "operario,pedreiro,construtor,worker,builder,engenheiro,mecanico",
    "superhero": "superheroi,super heroi,superhero,super homem,superman",
    "businessman": "empresario,executivo,chefe,gerente,businessman,ceo,advogado,politico,vendedor,influencer",
    "athlete": "atleta,jogador,corredor,esportista,athlete,player,runner,lutador,boxeador",
    "ninja": "ninja,samurai",
    "pirate": "pirata,pirate,capitao,marinheiro,sailor",
    "vampire": "vampiro,dracula,vampire,conde",
    "zombie": "zumbi,zombie,morto vivo",
    "angel": "anjo,angel",
    "student": "estudante,aluno,aluna,student",
    "statue": "estatua,statue,monumento,escultura",
    "doll": "boneca,boneco,doll,manequim,marionete",
    "caveman": "homem das cavernas,caveman,primitivo,neandertal",
    "diver": "mergulhador,diver",
    "fisherman": "pescador,fisherman",
    "driver": "motorista,caminhoneiro,taxista,driver,trucker,piloto,pilot",
    "musician": "musico,cantor,cantora,guitarrista,musician,singer,dj,rockstar",
    "policeman": "policial,policia,guarda,detetive,police,cop,detective,investigador,xerife",
    "nurse": "enfermeira,enfermeiro,nurse",
    "saci": "saci,saci perere",
    "curupira": "curupira",
    "mermaid": "sereia,iara,mermaid",
    # animais
    "cat": "gato,gata,gatinho,felino,cat,kitten,bichano",
    "dog": "cachorro,cao,cadela,cachorrinho,filhote,dog,puppy,vira lata",
    "fox": "raposa,fox",
    "wolf": "lobo,loba,lobisomem,wolf,werewolf",
    "jaguar": "onca,onca pintada,jaguar,leopardo,leopard,guepardo,cheetah,puma,pantera",
    "tiger": "tigre,tiger",
    "lion": "leao,leoa,lion",
    "horse": "cavalo,egua,potro,horse,pony,mula,burro,jumento,donkey,mula sem cabeca",
    "unicorn": "unicornio,unicorn,pegasus,pegaso",
    "cow": "vaca,boi,touro,bezerro,cow,bull,ox,minotauro",
    "pig": "porco,porquinho,leitao,pig",
    "sheep": "ovelha,carneiro,cordeiro,sheep,lamb",
    "capybara": "capivara,capybara",
    "bear": "urso,ursinho,bear,mapinguari,urso de pelucia,teddy",
    "panda": "panda",
    "rabbit": "coelho,coelhinho,lebre,rabbit,bunny,hare",
    "mouse": "rato,ratinho,camundongo,mouse,rat,hamster",
    "elephant": "elefante,elephant,mamute,mammoth",
    "deer": "veado,cervo,alce,rena,deer,reindeer,moose",
    "dinosaur": "dinossauro,dinossauros,dino,dinosaur,trex,t rex,tiranossauro,brontossauro",
    "dragon": "dragao,dragon,wyvern,dragaozinho",
    "turtle": "tartaruga,tartaruguinha,jabuti,cagado,turtle,tortoise",
    "frog": "sapo,ra,perereca,frog,toad",
    "monkey": "macaco,mico,gorila,chimpanze,monkey,gorilla,ape",
    "camel": "camelo,dromedario,camel",
    "goat": "cabra,bode,goat",
    # aves
    "bird": "passaro,ave,passarinho,bird,sabia,beija flor,hummingbird",
    "parrot": "papagaio,arara,periquito,parrot,macaw",
    "owl": "coruja,owl,mocho",
    "eagle": "aguia,falcao,gaviao,eagle,hawk,falcon,condor,urubu,abutre",
    "penguin": "pinguim,penguin",
    "chicken": "galinha,galo,pintinho,frango,chicken,rooster,hen,chick",
    "duck": "pato,patinho,ganso,duck,goose",
    "bat": "morcego,bat",
    "pigeon": "pombo,pomba,pigeon,dove",
    "flamingo": "flamingo",
    "toucan": "tucano,toucan",
    # aquáticos e criaturas
    "fish": "peixe,peixes,peixinho,fish,piaba,cardume",
    "shark": "tubarao,shark",
    "whale": "baleia,whale,orca",
    "dolphin": "golfinho,dolphin",
    "pink_dolphin": "boto,boto cor de rosa,pink dolphin",
    "clownfish": "peixe palhaco,nemo,clownfish",
    "goldfish": "peixe dourado,goldfish",
    "piranha": "piranha",
    "octopus": "polvo,lula,octopus,squid,kraken",
    "jellyfish": "agua viva,jellyfish",
    "snake": "cobra,serpente,jiboia,sucuri,anaconda,snake,serpent,jormungandr",
    "fire_snake": "boitata,serpente de fogo,fire snake",
    "butterfly": "borboleta,mariposa,butterfly,moth",
    "ant": "formiga,formigas,ant,ants",
    "bee": "abelha,vespa,bee,wasp",
    "ladybug": "joaninha,ladybug",
    "spider": "aranha,spider,tarantula",
    # objetos
    "block": "bloco,blocos,cubo,cubos,block,blocks,cube,cubes,peca,pecas",
    "brick": "lego,legos,tijolo,tijolos,brick,bricks",
    "domino": "domino,dominos,dominoes",
    "dice": "dado,dados,dice,die",
    "ball": "bola,bolas,ball,bola de praia,beach ball",
    "marble": "bolinha de gude,gude,marble,marbles,bolinha,bolinhas",
    "pyramid_block": "piramide de brinquedo",
    "cylinder": "cilindro,cylinder",
    "star": "estrela,estrelas,estrelinha,star,stars",
    "heart": "coracao,coracoes,heart,amor,love",
    "coin": "moeda,moedas,dinheiro,coin,coins,money,cash,dolar,ouro",
    "gem": "joia,diamante,pedra preciosa,rubi,esmeralda,gem,diamond,jewel",
    "crystal": "cristal,cristais,crystal,quartzo",
    "gear": "engrenagem,engrenagens,gear,gears,cog",
    "ring": "anel,aro,argola,ring,portal",
    "balloon": "balao,baloes,bexiga,balloon,balloons",
    "gift": "presente,presentes,caixa de presente,gift,present",
    "tree": "arvore,arvores,tree,trees,carvalho,oak,ipe",
    "pine": "pinheiro,pinheiros,pine,abeto,arvore de natal,christmas tree",
    "palm": "palmeira,coqueiro,palm,coconut tree",
    "dead_tree": "arvore seca,arvore morta,galho seco,dead tree",
    "bush": "arbusto,moita,bush,shrub",
    "flower": "flor,flores,rosa,girassol,flower,flowers,rose,sunflower,tulipa,semente",
    "mushroom": "cogumelo,cogumelos,mushroom,fungo",
    "rock": "pedra,pedras,rocha,rock,stone,boulder",
    "cactus": "cacto,cactos,cactus,mandacaru",
    "log": "tronco,lenha,log",
    "seaweed": "alga,algas,seaweed,kelp",
    "coral": "coral,corais,recife",
    "mountain": "montanha,morro,monte,mountain,hill",
    "volcano": "vulcao,volcano,vesuvio",
    "cloud": "nuvem,nuvens,cloud,clouds",
    "rainbow": "arco iris,rainbow",
    "grass": "grama,capim,grass",
    "snowman": "boneco de neve,snowman",
    "house": "casa,casinha,house,home,lar,chale",
    "building": "predio,predios,edificio,arranha ceu,building,skyscraper",
    "tower": "torre,tower",
    "castle": "castelo,palacio,castle,palace,fortaleza,reino",
    "temple": "templo,partenon,temple,igreja,church,catedral,santuario",
    "pyramid": "piramide,piramides,pyramid,pyramids",
    "column": "coluna,colunas,pilar,column,pillar",
    "hut": "cabana,oca,choupana,hut,iglu",
    "tent": "barraca,tenda,tent",
    "barn": "celeiro,estabulo,barn",
    "lighthouse": "farol,lighthouse",
    "windmill": "moinho,moinho de vento,windmill",
    "fence": "cerca,grade,fence",
    "tombstone": "tumulo,lapide,cova,tumba,tombstone,grave",
    "lamp": "poste,luminaria,street lamp,lamp post,lamp",
    "bench": "banco de praca,bench",
    "sign": "placa,letreiro,sign",
    "door": "porta,portao,door,gate",
    "elevator": "elevador,elevator,lift",
    "car": "carro,automovel,car,carro esportivo",
    "taxi": "taxi",
    "police_car": "viatura,carro de policia,police car",
    "bus": "onibus,bus,van",
    "truck": "caminhao,carreta,truck,lorry",
    "rocket": "foguete,nave,nave espacial,rocket,spaceship,spacecraft",
    "ufo": "ovni,disco voador,ufo,flying saucer,nave alienigena",
    "airplane": "aviao,aeronave,jato,airplane,plane,jet,14 bis,aviaozinho",
    "boat": "barco,canoa,jangada,bote,boat,canoe,raft",
    "ship": "navio,titanic,caravela,ship,galeao,transatlantico",
    "submarine": "submarino,submarine",
    "satellite": "satelite,satellite,sonda,sputnik",
    "train": "trem,locomotiva,metro,train",
    "planet": "planeta,planetas,planet,planets,exoplaneta",
    "earth": "terra,planeta terra,globo,earth,globe",
    "mars": "marte,mars,planeta vermelho",
    "jupiter": "jupiter",
    "saturn": "saturno,saturn",
    "moon": "lua,moon",
    "neptune": "netuno,neptune,urano,uranus",
    "venus": "venus,mercurio",
    "sun": "sol,sun",
    "black_hole": "buraco negro,black hole,singularidade",
    "asteroid": "asteroide,asteroides,meteoro,meteorito,asteroid,meteor",
    "comet": "cometa,comet",
    "galaxy": "galaxia,via lactea,galaxy,nebulosa",
    "table": "mesa,table,escrivaninha,desk",
    "chair": "cadeira,chair,trono,throne",
    "bed": "cama,bed,berco",
    "sofa": "sofa,couch",
    "tv": "televisao,tv,televisor,monitor,tela,screen",
    "computer": "computador,pc,computer",
    "laptop": "notebook,laptop",
    "phone": "celular,telefone,smartphone,phone,iphone",
    "book": "livro,livros,caderno,book,manuscrito,diario,voynich",
    "candle": "vela,velas,candle",
    "campfire": "fogueira,campfire",
    "fire": "fogo,chamas,incendio,fire,flames",
    "torch": "tocha,torch",
    "lantern": "lanterna,lampiao,lantern",
    "clock": "relogio,clock,watch,ampulheta,hourglass",
    "chest": "bau,cofre,chest",
    "treasure": "tesouro,treasure",
    "box": "caixa,caixote,box,crate,pacote",
    "barrel": "barril,tonel,barrel",
    "cauldron": "caldeirao,cauldron",
    "bottle": "garrafa,frasco,bottle",
    "potion": "pocao,potion,elixir",
    "beaker": "tubo de ensaio,beaker,flask,proveta",
    "cup": "copo,xicara,cup",
    "coffee": "cafe,coffee,cafezinho,expresso",
    "mug": "caneca,mug",
    "lightbulb": "lampada,ideia,lightbulb,bulb,idea",
    "tape": "fita,fita vhs,vhs,cassete,tape,videotape",
    "sword": "espada,sabre,sword,katana",
    "shield": "escudo,shield",
    "hammer": "martelo,hammer,mjolnir",
    "crown": "coroa,crown",
    "trophy": "trofeu,taca,trophy,medalha",
    "flag": "bandeira,flag",
    "magnifier": "lupa,magnifier,magnifying glass",
    "arrow": "seta,flecha,arrow",
    "lightning": "raio,relampago,lightning,thunder,bolt",
    "atom": "atomo,atomos,atom,eletron",
    "dna": "dna,gene,genes,genetica",
    "molecule": "molecula,moleculas,molecule,cafeina",
    "cell": "celula,celulas,cell",
    "virus": "virus",
    "bacteria": "bacteria,bacterias,germe,germes,microbio",
    "brain": "cerebro,mente,brain,neuronio,neuronios",
    "magnet": "ima,magnet",
    "pizza": "pizza",
    "cake": "bolo,torta,cake",
    "apple": "maca,fruta,frutas,apple,fruit",
    "donut": "rosquinha,donut",
    "bread": "pao,pao de forma,bread,loaf,torrada",
    "croissant": "croissant",
    "icecream": "sorvete,picole,ice cream",
    "candy": "doce,doces,bala,balas,chocolate,pirulito,candy,sweets",
    "egg": "ovo,ovos,egg",
    "burger": "hamburguer,lanche,burger,sanduiche",
    "banana": "banana",
}

SETTING_WORDS = {
    "forest": "floresta,bosque,mata,forest,woods",
    "jungle": "selva,floresta tropical,amazonia,amazonas,jungle,rainforest,mata atlantica",
    "park": "parque,praca,jardim,park,garden",
    "city": "cidade,rua,avenida,city,street,downtown,metropole,centro da cidade",
    "village": "vila,vilarejo,aldeia,povoado,village,town",
    "farm": "fazenda,sitio,roca,chacara,farm,ranch,rancho",
    "desert": "deserto,sertao,desert,caatinga,duna,dunas",
    "egypt": "egito,egypt,cairo,giza",
    "beach": "praia,litoral,beach,shore,areia",
    "ocean": "oceano,mar,alto mar,sea,ocean,ondas,triangulo das bermudas",
    "river": "rio,lago,lagoa,margem,river,lake,pond,igarape",
    "underwater": "fundo do mar,debaixo d agua,underwater,oceano profundo,deep sea,abissal",
    "mountains": "montanhas,serra,mountains,everest,cume,pico,topo da montanha",
    "snow": "neve,gelo,inverno,polo,antartida,artico,snow,ice,winter,arctic,iceberg",
    "cave": "caverna,gruta,mina,tunel,cave,cavern,mine,tunnel,labirinto,labyrinth",
    "graveyard": "cemiterio,graveyard,cemetery",
    "room": "quarto,sala,cozinha,kitchen,bedroom,living room,room,interior,apartamento,brecho",
    "office": "escritorio,empresa,office,escola,sala de aula,classroom,school",
    "lab": "laboratorio,lab,laboratory,hospital,clinica",
    "stage": "palco,teatro,show,concerto,stage,theater,auditorio",
    "studio": "estudio,studio,fundo branco,abstrato",
    "space": "espaco,universo,cosmos,espaco sideral,space,universe,orbita,galaxia",
    "moon": "superficie da lua,lua,moon surface",
    "mars": "marte,mars,planeta vermelho",
    "sky": "ceu,sky,nas nuvens,acima das nuvens",
    "temple": "templo,grecia,olimpo,partenon,temple,greece,roma,coliseu",
    "castle": "castelo,reino,medieval,castle,kingdom",
    "volcano": "vulcao,pompeia,lava,volcano",
    "road": "estrada,rodovia,autoestrada,road,highway,caminho",
}

TIME_WORDS = {
    "day": "dia,manha,tarde,day,morning,afternoon,noon,meio dia",
    "sunset": "por do sol,entardecer,anoitecer,crepusculo,sunset,dusk,fim de tarde",
    "dawn": "amanhecer,aurora,nascer do sol,dawn,sunrise,madrugada clara",
    "night": "noite,madrugada,meia noite,night,midnight,escuro,dark,3h,3 da manha",
}

WEATHER_WORDS = {
    "none": "nenhum,limpo,clear,none,sem",
    "rain": "chuva,chuvoso,chovendo,rain,rainy",
    "storm": "tempestade,temporal,storm,trovoada,raios",
    "snow": "neve,nevando,snow,snowing,nevasca",
    "fog": "neblina,nevoa,fog,mist,bruma,nevoeiro",
    "fireflies": "vagalumes,vaga lumes,fireflies,firefly,vagalume",
    "sparkles": "brilho,brilhos,magia,magica,sparkles,glitter,estrelinhas",
    "bubbles": "bolhas,bubbles",
    "embers": "brasas,faiscas,embers,cinzas,sparks",
    "confetti": "confete,confetes,festa,confetti,party",
    "leaves": "folhas,outono,leaves,autumn,fall leaves",
    "dust": "poeira,dust,po",
    "petals": "petalas,petals",
}

CAMERA_WORDS = {
    "orbit": "orbita,orbitar,girar,orbit,rotate,around",
    "dolly_in": "aproximar,zoom in,dolly in,push in,aproximacao",
    "dolly_out": "afastar,zoom out,dolly out,pull out,pull back",
    "pan_left": "pan esquerda,pan left",
    "pan_right": "panoramica,pan,pan direita,pan right",
    "crane_up": "subir,grua,crane,crane up,elevar",
    "crane_down": "descer,crane down,baixar",
    "static": "parada,fixa,static,still,locked",
    "low_angle": "de baixo,contra plongee,low angle,heroic",
    "top_down": "de cima,aerea,top down,drone,birds eye,vista de cima",
    "follow": "seguir,acompanhar,follow,tracking,travelling",
    "shake": "tremida,camera na mao,handheld,shake,shaky",
    "spiral": "espiral,spiral",
    "reveal": "revelar,reveal,revelacao",
    "closeup": "close,rosto,closeup,close up,detalhe",
    "flyover": "sobrevoo,flyover,fly over",
}

ACTION_WORDS = {
    "idle": "parado,idle,stand,ficar,esperar,wait,standing,respirar",
    "walk": "andando,caminhando,passeando,marchando,andar,anda,caminhar,caminha,walk,walking,passear,marchar,march,seguir em frente",
    "run": "correr,corre,correndo,fugindo,run,running,fugir,flee,escapar,disparar",
    "jump": "pulando,saltando,pular,pula,saltar,salta,jump,jumping,hop,pulo",
    "wave": "acenando,acenar,acena,tchau,oi,wave,waving,cumprimentar,greet",
    "dance": "dancando,dancar,danca,dance,dancing,rebolar",
    "cheer": "comemorando,celebrando,comemorar,comemora,celebrar,vibrar,cheer,celebrate,festejar,vitoria",
    "point": "apontar,aponta,point,mostrar,show,indicar",
    "think": "pensando,pensar,pensa,think,thinking,duvida,refletir,imaginar,curioso",
    "scared": "assustada,com medo,tremendo de medo,assustado,assustar se,medo,scared,afraid,fear,panico,terror,susto",
    "fall": "caindo,cair,cai,tropecar,fall,trip,desmaiar,faint",
    "sit": "sentando,sentar,senta,sentado,sit,sitting",
    "sleep": "dormindo,deitado,dormir,dorme,sleep,sleeping,deitar,lie down,descansar,rest,sonhar,dream",
    "talk": "falando,conversando,cantando,falar,fala,conversar,talk,talking,contar,explicar,explain,dizer,say,cantar,sing",
    "fly": "voar,voa,voando,planando,fly,flying,planar",
    "swim": "nadar,nada,nadando,mergulhando,swim,swimming,mergulhar,dive",
    "look": "olhando,procurando,observando,explorando,olhar,olha,procurar,observar,look,search,explorar,explore,investigar,vigiar",
    "clap": "aplaudir,aplaude,clap,palmas,applaud",
    "bow": "reverencia,curvar,bow,agradecer",
    "spin": "girando,rodando,girar,gira,rodar,spin,spinning,rotate,rodopiar,piruetar",
    "attack": "atacando,lutando,atacar,ataca,lutar,golpe,attack,fight,batalha,battle,duelo,enfrentar",
    "push": "empurrar,empurra,push,carregar,carry",
    "kneel": "ajoelhar,rezar,kneel,pray,orar,implorar",
    "climb": "escalando,escalar,escala,climb,climbing,trepar",
    "scare": "assombrar,assusta,scare,haunt,boo,atormentar",
    "wag": "abanar,abanar rabo,wag,feliz",
    "eat": "comendo,bebendo,comer,come,eat,eating,beber,drink,mastigar",
    "howl": "uivar,uiva,howl,rugir,roar,urrar",
    "circle": "circular,rodear,circle,sobrevoar,dar voltas",
    "bounce": "quicando,quicar,quica,bounce,bouncing",
    "float": "flutuando,levitando,flutuar,flutua,levitar,float,hover,levitate,pairar",
    "drop": "despencar,drop,cair do ceu,chover objetos",
    "grow": "crescendo,crescer,cresce,grow,aumentar,expandir,brotar",
    "pop": "pop,surgir,surge,brotar do nada",
    "appear": "aparecer,aparece,appear,materializar,revelar",
    "shrink": "encolher,encolhe,shrink,diminuir",
    "vanish": "sumindo,desaparecendo,sumir,some,desaparecer,vanish,disappear,evaporar",
    "shake": "tremer,treme,shake,vibrar,sacudir",
    "pulse": "pulsar,pulsa,pulse,batida,bater,beat,piscar luz",
    "wobble": "balancar,balanca,wobble,bambolear",
    "orbit": "orbitar,orbita,orbit,orbiting,gravitar",
    "roll": "rolando,rolar,rola,roll,rolling",
    "tumble": "tombar,tomba,tumble,capotar",
    "slide": "deslizar,desliza,slide,escorregar",
    "rise": "subindo,subir,sobe,rise,levantar,erguer,emergir,surgir do chao",
    "sink": "afundando,afundar,afunda,sink,submergir,naufragar",
    "approach": "aproximar,aproxima,approach,vir,chegar,arrive,avancar",
    "retreat": "afastar,afasta,retreat,ir embora,leave,recuar,partir",
    "swing": "pendulo,swing,balancar pendurado",
    "flip": "cambalhota,mortal,flip,capotar no ar",
    "glow": "brilhando,brilhar,brilha,glow,acender,iluminar,light up",
    "open": "abrir,abre,open,destrancar",
    "drive": "dirigindo,navegando,dirigir,dirige,drive,driving,acelerar,navegar,sail,pilotar",
    "launch": "decolando,decolar,decola,lancar,launch,takeoff,liftoff",
    "explode": "explodindo,explodir,explode,estourar,explosion,boom,destruir,desmoronar",
    "stack": "empilhando,empilhar,empilha,stack,stacking,torre de blocos",
    "build": "construindo,montando,construir,constroi,montar,monta,build,building,erguer construcao",
    "domino": "domino,efeito domino,em sequencia",
    "scatter": "espalhar,espalha,scatter,dispersar",
    "assemble": "juntar,junta,reunir,assemble,unir,agrupar",
    "rain": "chover,chovendo moedas,rain down,cair como chuva",
    "group_wave": "ola,group wave,onda",
    "carousel": "carrossel,roda gigante,carousel,girar em roda",
    "sway": "ventar,sway,balancar ao vento",
    "blink": "piscar,pisca,blink,blinking",
}

FORMATION_WORDS = {
    "row": "fila,linha,row,lado a lado,side by side",
    "line": "coluna,column,line,em fila indiana",
    "circle": "circulo,roda,circle,ring,around",
    "grid": "grade,grid,matriz",
    "stack": "pilha,torre,stack,tower,empilhado",
    "pyramid": "piramide,pyramid",
    "wall": "parede,muro,wall",
    "scatter": "espalhado,aleatorio,scatter,random,espalhados",
    "arc": "arco,semicirculo,arc",
    "crowd": "multidao,grupo,crowd,bando,turma",
    "v": "v,em v,v formation",
    "diagonal": "diagonal,em diagonal",
}

POSITION_WORDS = {
    "center": "centro,meio,center,middle,centre",
    "left": "esquerda,left",
    "right": "direita,right",
    "back": "atras,fundo,back,behind,background",
    "front": "frente,front,foreground,primeiro plano",
    "far": "longe,distante,far,horizonte,horizon",
    "sky": "ceu,sky,no ar,in the air,no alto",
    "above": "acima,em cima,sobre,above,over,overhead,acima da cabeca,sobre a cabeca",
    "around": "ao redor,em volta,around,surrounding",
}

FACING_WORDS = {
    "camera": "camera,frente,front,viewer,espectador",
    "left": "esquerda,left",
    "right": "direita,right",
    "away": "costas,away,back,de costas",
    "center": "centro,center,each other,um para o outro,frente a frente",
}

COLORS = {
    "vermelho,red,vermelha,escarlate": "#e53935",
    "laranja,orange": "#fb8c00",
    "amarelo,yellow,amarela": "#fdd835",
    "verde,green": "#43a047",
    "verde claro,light green,lima,lime": "#9ccc65",
    "verde escuro,dark green": "#2e7d32",
    "azul,blue": "#1e88e5",
    "azul claro,light blue,celeste": "#81d4fa",
    "azul escuro,navy,marinho": "#1a237e",
    "roxo,purple,violeta,violet,lilas,roxa": "#8e24aa",
    "rosa,pink,rosado": "#f06292",
    "branco,white,branca": "#f5f5f5",
    "preto,black,preta": "#1b1b1f",
    "cinza,gray,grey,cinzento": "#8d8f95",
    "marrom,brown,castanho": "#795548",
    "dourado,gold,golden,ouro": "#ffc83d",
    "prateado,silver,prata": "#c9ced6",
    "bege,beige,creme,cream": "#e8d5b0",
    "ciano,cyan,turquesa,turquoise,agua": "#26c6da",
    "vinho,burgundy,bordo": "#7b1f2e",
    "magenta,fucsia": "#d81b60",
}

TYPE_INDEX = _index(TYPE_WORDS)
SETTING_INDEX = _index(SETTING_WORDS)
TIME_INDEX = _index(TIME_WORDS)
WEATHER_INDEX = _index(WEATHER_WORDS)
CAMERA_INDEX = _index(CAMERA_WORDS)
ACTION_INDEX = _index(ACTION_WORDS)
FORMATION_INDEX = _index(FORMATION_WORDS)
POSITION_INDEX = _index(POSITION_WORDS)
FACING_INDEX = _index(FACING_WORDS)
COLOR_INDEX = {plain(w): hexv for words, hexv in COLORS.items() for w in words.split(",")}

CAMERAS = tuple(CAMERA_WORDS)
WEATHERS = tuple(WEATHER_WORDS)
FORMATIONS = tuple(FORMATION_WORDS)
POSITIONS = tuple(POSITION_WORDS)


def lookup(value, index: dict[str, str], valid=None) -> str:
    """Acha o nome interno: frase inteira, depois pedaços de 3, 2 e 1 palavra."""
    v = plain(value)
    if not v:
        return ""
    if v in index and (valid is None or index[v] in valid):
        return index[v]
    v2 = v.replace(" ", "_")
    if valid is not None and v2 in valid:
        return v2
    words = v.split()
    for size in (3, 2, 1):
        for i in range(len(words) - size + 1):
            key = " ".join(words[i : i + size])
            hit = index.get(key)
            if hit and (valid is None or hit in valid):
                return hit
    return ""


def scan(text: str, index: dict[str, str], valid=None, limit: int = 6) -> list[str]:
    """Todos os nomes internos encontrados num texto livre, na ordem em que aparecem."""
    words = plain(text).split()
    found: list[tuple[int, str]] = []
    taken = [False] * len(words)
    for size in (3, 2, 1):
        for i in range(len(words) - size + 1):
            if any(taken[i : i + size]):
                continue
            hit = index.get(" ".join(words[i : i + size]))
            if hit and (valid is None or hit in valid):
                found.append((i, hit))
                for k in range(i, i + size):
                    taken[k] = True
    out: list[str] = []
    for _i, hit in sorted(found):
        if hit not in out:
            out.append(hit)
    return out[:limit]


def parse_color(value):
    if value is None or value == "":
        return None
    if isinstance(value, (list, tuple)) and len(value) == 3:
        try:
            c = [float(x) for x in value]
            return tuple(x / 255 if max(c) > 1 else x for x in c)
        except (TypeError, ValueError):
            return None
    s = str(value).strip()
    if re.fullmatch(r"#?[0-9a-fA-F]{6}|#?[0-9a-fA-F]{3}", s):
        return hex_rgb(s)
    key = plain(s)
    if key in COLOR_INDEX:
        return hex_rgb(COLOR_INDEX[key])
    for w in key.split():
        if w in COLOR_INDEX:
            return hex_rgb(COLOR_INDEX[w])
    return None


def _num(value, default: float, lo: float, hi: float) -> float:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return default
    if x != x:  # NaN
        return default
    return min(max(x, lo), hi)


def _actions(value, cat: str) -> list[str]:
    if isinstance(value, str):
        items = re.split(r"[,;/>|]|\bthen\b|\bdepois\b|\be\b|\band\b", value)
    elif isinstance(value, (list, tuple)):
        items = [str(x) for x in value]
    else:
        items = []
    out = []
    for it in items:
        a = lookup(it, ACTION_INDEX, ACTIONS)
        if not a and plain(it).replace(" ", "_") in ACTIONS:
            a = plain(it).replace(" ", "_")
        if a and (not out or out[-1] != a):
            out.append(a)
    return out[:4]


def normalize_actor(raw) -> ActorSpec | None:
    if isinstance(raw, str):
        raw = {"type": raw}
    if not isinstance(raw, dict):
        return None
    kind = lookup(
        raw.get("type") or raw.get("model") or raw.get("name") or raw.get("kind") or "",
        TYPE_INDEX,
        M.REGISTRY,
    )
    if not kind:
        kind = plain(raw.get("type", "")).replace(" ", "_")
        if kind not in M.REGISTRY:
            return None
    cat = M.category(kind)
    acts = (
        raw.get("actions")
        or raw.get("action")
        or raw.get("animation")
        or raw.get("animations")
        or raw.get("do")
        or []
    )
    actions = _actions(acts, cat) or ["idle"]
    count = int(_num(raw.get("count", raw.get("quantity", 1)), 1, 1, M.REGISTRY[kind].max_count))
    form = lookup(raw.get("formation", ""), FORMATION_INDEX, FORMATIONS)
    pos = lookup(raw.get("position", raw.get("where", "")), POSITION_INDEX, POSITIONS)
    facing = lookup(raw.get("facing", ""), FACING_INDEX, FACING_WORDS)
    size = _num(raw.get("size", raw.get("scale", 1.0)), 1.0, 0.2, 6.0)
    return ActorSpec(kind, count, actions, form, pos, parse_color(raw.get("color")), size, facing)


def normalize_scene(
    raw, text: str = "", theme_world: str = "studio", index: int = 0, default_actor: str = "person"
) -> SceneSpec:
    """Transforma o `scene3d` da IA (ou nada) numa cena válida."""
    raw = raw if isinstance(raw, dict) else {}
    hint = " ".join(str(raw.get(k, "")) for k in ("description", "image_prompt", "prompt")) + " " + text
    setting = lookup(raw.get("setting", raw.get("location", raw.get("cenario", ""))), SETTING_INDEX, SETTINGS)
    setting = setting or (scan(hint, SETTING_INDEX, SETTINGS, 1) or [""])[0] or theme_world
    if setting not in SETTINGS:
        setting = "studio"
    time = (
        lookup(raw.get("time", ""), TIME_INDEX, TIMES)
        or (scan(hint, TIME_INDEX, TIMES, 1) or [""])[0]
        or SETTINGS[setting].time
    )
    weather = (
        lookup(raw.get("weather", ""), WEATHER_INDEX, WEATHERS)
        or (scan(hint, WEATHER_INDEX, WEATHERS, 1) or ["none"])[0]
    )
    camera = lookup(raw.get("camera", ""), CAMERA_INDEX, CAMERAS)
    actors_raw = raw.get("actors") or raw.get("objects") or raw.get("characters") or []
    if isinstance(actors_raw, (dict, str)):
        actors_raw = [actors_raw]
    actors = [a for a in (normalize_actor(x) for x in actors_raw[:6]) if a is not None]
    if not actors:
        kinds = scan(hint, TYPE_INDEX, M.REGISTRY, 3)
        acts = scan(hint, ACTION_INDEX, ACTIONS, 2)
        for i, k in enumerate(kinds or [default_actor]):
            actors.append(ActorSpec(k, 1, acts if i == 0 and acts else ["idle"]))
    total = 0
    for a in actors:  # limite de instâncias para manter a renderização leve
        a.count = max(1, min(a.count, 60 - total))
        total += a.count
    return SceneSpec(setting, time, weather or "none", camera, actors)


# ------------------------------------------------------------------ catálogo para a IA
def catalog_text() -> str:
    groups: dict[str, list[str]] = {
        "person": [],
        "animal": [],
        "bird": [],
        "fish": [],
        "creature": [],
        "insect": [],
        "prop": [],
    }
    for k, e in M.REGISTRY.items():
        groups.setdefault(e.cat, []).append(k)
    people = ", ".join(groups["person"])
    animals = ", ".join(groups["animal"])
    birds = ", ".join(groups["bird"] + groups["insect"])
    water = ", ".join(groups["fish"] + groups["creature"])
    props = ", ".join(groups["prop"])
    return f"""CATÁLOGO 3D (o vídeo é montado com modelos 3D prontos; use SOMENTE estes nomes, em inglês):
- setting: {", ".join(SETTINGS)}
- time: day, sunset, dawn, night
- weather: {", ".join(WEATHERS)}
- camera: {", ".join(CAMERAS)}
- actors[].type
  pessoas: {people}
  animais: {animals}
  aves e insetos: {birds}
  água e criaturas: {water}
  objetos: {props}
- actors[].actions (lista em ordem; dividem o tempo da cena):
  pessoas: idle, walk, run, jump, wave, dance, cheer, point, think, scared, fall, sit, sleep, talk, fly, swim, look, clap, bow, spin, attack, push, kneel, climb, approach, retreat
  animais: idle, walk, run, jump, sit, sleep, wag, eat, look, howl, approach, retreat
  aves/insetos: idle, fly, circle, walk, eat | água: swim, idle, jump, circle
  objetos: idle, spin, bounce, float, drop, grow, pop, appear, shrink, vanish, shake, pulse, wobble, orbit, roll, tumble, slide, rise, sink, fly, approach, retreat, swing, flip, glow, open, drive, launch, explode
  grupos (count > 1): stack, build, domino, explode, scatter, assemble, rain, group_wave, carousel (ou qualquer ação acima)
- actors[].formation (grupos): {", ".join(FORMATIONS)}
- actors[].position: {", ".join(POSITIONS)}
- actors[].color: "#RRGGBB" (opcional) | size: 0.3 a 5 (1 = tamanho normal) | count: 1 a 30
- actors[].facing: camera, left, right, away, center"""


# ------------------------------------------------------------------ diretor sem IA
PLANS = {
    "person": [
        ["walk", "wave"],
        ["look", "point"],
        ["think"],
        ["jump", "cheer"],
        ["talk"],
        ["dance"],
        ["scared"],
        ["clap"],
    ],
    "ghost": [["float"], ["scare"], ["walk"], ["spin"], ["vanish"]],
    "animal": [["walk", "sit"], ["run"], ["jump"], ["wag"], ["look", "eat"], ["sleep"]],
    "bird": [["fly"], ["circle"], ["idle", "eat"], ["fly"]],
    "insect": [["fly"], ["circle"], ["walk"]],
    "fish": [["swim"], ["circle"], ["jump"], ["swim"]],
    "creature": [["swim"], ["idle"], ["circle"]],
    "prop": [["drop"], ["spin"], ["pop", "float"], ["bounce"], ["grow", "glow"], ["wobble"]],
}
CAM_CYCLE = ["dolly_in", "orbit", "pan_right", "crane_up", "spiral", "dolly_out", "low_angle", "orbit"]


def offline_script(prompt: str, n: int, theme_world: str = "studio", words: int = 8, hashtags=()) -> dict:
    """Roteiro sem IA: acha personagens, lugar e ações no texto e varia câmera e ações por cena."""
    kinds = scan(prompt, TYPE_INDEX, M.REGISTRY, 4)
    setting = (scan(prompt, SETTING_INDEX, SETTINGS, 1) or [theme_world])[0]
    time = (scan(prompt, TIME_INDEX, TIMES, 1) or [SETTINGS.get(setting, SETTINGS["studio"]).time])[0]
    weather = (scan(prompt, WEATHER_INDEX, WEATHERS, 1) or ["none"])[0]
    verbs = scan(prompt, ACTION_INDEX, ACTIONS, 3)
    chars = [k for k in kinds if M.category(k) != "prop"]
    props = [k for k in kinds if M.category(k) == "prop"]
    main = (chars or props or ["person"])[0]
    others = [k for k in kinds if k != main][:2]
    cat = M.category(main) if main not in ("ghost",) else "ghost"
    plans = PLANS.get(cat, PLANS["prop"])
    tokens = str(prompt).split()
    per = max(1, min(words, -(-len(tokens) // max(n, 1))))
    chunks = [" ".join(tokens[i : i + per]) for i in range(0, len(tokens), per)]
    color = None
    for w in plain(prompt).split():
        if w in COLOR_INDEX:
            color = COLOR_INDEX[w]
            break
    scenes = []
    for i in range(max(1, n)):
        acts = verbs if (i == 0 and verbs) else plans[i % len(plans)]
        actors = [{"type": main, "actions": acts, "color": color}]
        if others:
            o = others[i % len(others)]
            oc = M.category(o)
            oacts = PLANS.get(oc, PLANS["prop"])[(i + 1) % len(PLANS.get(oc, PLANS["prop"]))]
            actors.append({"type": o, "actions": oacts})
        scenes.append(
            {
                "text": chunks[i] if i < len(chunks) else "",
                "scene3d": {
                    "setting": setting,
                    "time": time,
                    "weather": weather,
                    "camera": CAM_CYCLE[i % len(CAM_CYCLE)],
                    "actors": actors,
                },
            }
        )
    return {
        "title": str(prompt)[:90],
        "caption": str(prompt)[:200],
        "hashtags": list(hashtags),
        "scenes": scenes,
    }
