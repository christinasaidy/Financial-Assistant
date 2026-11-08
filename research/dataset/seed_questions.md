# Seed questions for the dataset generator

Written by Christina. Qwen is shown these as examples of how people really ask, so it copies their style. They are
NOT test questions: never copy a test question here.
A third of each section was moved to the test set (research/evaluation/data/test_questions.json) on 2026-11-08,
before any generation, so Qwen never sees them.

How to fill it in:
- Under each template, write 2 or 3 questions after the dashes, the way you or your friends would type them.
- Mostly Arabizi; mix in English words wherever that is natural ("adde sraft 3al groceries?").
- Any item, shop or period is fine; the script swaps in its own. Use the examples in the descriptions if unsure.
- Add more dashes if you want more lines. Leave a line empty if you have nothing for it.
- Under "Arabizi words", add how people write each item or category, separated by commas, all spellings you know.

---

## T1 Total for a period
How much the user spent in total, e.g. last month.
1. aday sarafet hal shaher
2. aday sarafet el shaher li mara2
3. kam sarafet ekher 3 shhour
4. aday dafa3et masari hal jemaa
5. shou majmou3 masroufe el sene
6. aday sarafet men awal el shaher la halla2
7. shu ken masroufe bi ayloul
8. aday sarafet ekher 7 iyem
9. fik t2elle aday sarafet ben 1 w 15 teshreen el awal
10. baddi a3ref kam sarafet el osbou3 li mara2
11. shou total masroufe ekher shaher
12. lyom la7alo adde sarfet
13. 3tine el ra2em li biwaje3, adde sarfet hal sene

## T2 Total in dollars
 Total spending in US dollars, e.g. since September.
1. kam total masroufe bel USD hal shaher
2. eza mne7seb kel li dafa3to bel dollar aday byetla3
3. aday tole3 masroufe bel dollar hal sene
4. aday sarafet bel USD ekher 3 eshhor
5. 7awelle total masroufe la dollar men awal el sene la halla2
6. farjine majmou3 li dafa3to bel USD hal osbou3
7. nkasarna, aday sarafet bel dollar ekher jemaa
8. ma 3am estaw3ib el ar2am, 3tine masrouf hal shaher w 3tine ye bel dollar
9. kel li dafa3to mbere7 bel dollar, adde byetla3 el total
10. kam dollar sarle sarfe men awal el shaher
11. jame3le masroufe hal sene w 7awwel el total la USD
12. shou el damage bel dollar hal weekend

## T3 A category in a period
Spending on one category, e.g. Transport in October.
1. aday sarafet aal transport bi teshreen el awal
2. adde dafa3et aal akel hal shaher
3. aday tole3 aalaye el benzin hal jemaa
4. shu sert sarfe 3al ahwe heda el shaher
5. adde sarafet aal mata3em el shaher li mara2
6. aday dafa3et aal groceries ekher 3 shhour
7. aday tayyaret masari aal shopping hal jemaa
8. nkasarna men el akel, adaysh sarafit 3a batne
9. ya wayle adde sarfet 3al delivery hal shaher
10. 7seble adde kallefne el akel barra ekher jem3ten
11. adde kabbet masare 3al makeup hal sene
12. el benzin akal ma3ashe, adde sarfet 3le bi teshreen
13. ma t2elle adde sarfet 3al tyeb hal shaher... la 3anjad 7seble
14. adde tole3 3laye el snacks hal jem3a
15. 7asse kel masriyete ra7o 3al taxi, adde dafa3et hal shaher
16. adde kellafne el gym men awal el sene
17. baddal ma dal etfeja2, farjine adde sarfet 3al groceries bi ayloul
18. bala el akel w bala shi, bde bas masrouf el na2el bi october
19. taleta aday ba3za2et aa tyeb

## T4 Where the money went
A breakdown of spending by category, e.g. this month.
1. wen ra7o mosriyete hal shaher
2. farjine masroufe hal jemaa category category
3. 3a shu sarafet kel hal masari el shaher li mara2
4. akel w benzin w shopping, adde sarafet 3a kel wehde hal shaher
5. baddi a3ref kif twazza3 masroufe ekher 3 shhour
6. shu akhad men jaybte hal shaher, farjine el tafasil 7asab no3 el masrouf
7. el ma3ash tar, 3a shu waza3to hal shaher
8. 3tine breakdown la masroufe el jemaa li mar2it
9. ta na3ref wen el meshkle, farjine masrouf hal shaher m2assam
10. kel hal dafe3 3a shu, rattible masrouf mbere7 7asab el category
11. farjine kif twaza3it masriyete ben el categories hal weekend
12. hal shaher shu sarafet 3al akel w el tyeb w kel shi tene

## T5 Top categories
The categories with the most spending, e.g. the top 3 last month.
1. shou aktar no3 masrouf akal el ma3ash hal shaher
2. wen ken aktar tbe3zi2 ekher 3 shhour
3. akel walla tyeb walla shu, aa shu sarafet aktar shi hal shaher
4. aya category sa7abit menne aktar masari el jemaa li mar2it
5. baddi a3ref aktar 3 ashya sarafet 3alayon men awal el sene
6. min el methem el ra2ise, aya category akhadit aktar shi hal shaher
7. farjine el top 5 taba3 hal shaher 7asab masroufe
8. adde sarafet aa aktar category kallefetne bi teshreen el awal
9. wen 3am bi sir aktar shi saref hal shaher
10. aya categories akalo akbar 7essa men masriyete ekher shaher

## T6 A shop in a period
Spending at one shop, e.g. Spinneys this year.

1. 7seble kel li dafa3to 3and Malak el Tawouk hal shaher
2. adaysh takayt masari bi Zara el shaher li mara2
3. shu tole3 majmou3 fawatire men Spinneys bi ayloul
4. farjine total masroufe bi Hawa Chicken ekher 3 shhour
5. adde kalafouni talabet Zaatar w Zeit men awal el shaher
6. Hesa hali fet7a hseb 3end macdo adday sarefet 
7. jame3le fwetir Fahed men 1 la 15 teshreen el awal w 3tine el total
8. baddi bas masroufe bi carrefour el jemaa li mar2it
9. adde dafa3et 3and Abou Jihad mbere7
10. shu sarle def3a bi Dunkin men nhar el a7ad la halla2
11. ma ken lezim fout 3a Zara, adde sarfet honik mbere7
12. adde akhad menne Burger King bi october
13. kel marra b2oul ekher talab, adde sarfet 3and Roadster hal shaher
14. adde dafa3et bi Decathlon men awal el sene la halla2

## T7 Top shop
The shop with the most spending, e.g. since September.
1. aya mahal sarafet fi aktar shi hal shaher
2. 3and min taraket aktar masari men ayloul la halla2
3. shu aktar mahal akal ma3ashe el shaher li mara2
4. farjine el mahal li dafa3etlo aktar shi hal sene
5. aktar masriyete la aya mahal ra7o hal jemaa
6. 7asse 3am beshteghil la mahal wa7ad, aya wa7ad ekher 3 shhour
7. wen ba3za2et aktar shi hal weekend
8. min aktar mahal mestafid menne hal sene
9. aya shop elo akbar 7essa men masroufe bi teshreen el awal
10. Spinneys walla ghayro, wen sarafet aktar shi hal shaher
11. baddi esm el mahal li sarafet fi aktar shi el jemaa li mar2it
12. shakle 3am edfa3 ma3ash el mwazafin, min aktar mahal dafa3etlo hal shaher
13. men ben kel el ma7allet li shteret menna hal weekend, aya wa7ad akhad aktar shi
14. baddi a3ref wen sarafet aktar shi mbere7, esm el mahal w el total
  
## T8 Visits to a shop
How many times the user went to a shop, e.g. Carrefour last month.

1. kam marra mara2et 3a Wooden Bakery hal jemaa
2. saro ya3rfoune bi Maison M, kam marra re7et hal shaher
3. O&C ekher 3 shhour, kam marra shtarayt men 3andon
4. 7asse kel layle bi Hibou, kam marra re7et hal jemaa la honik
5. men awal el sene la halla2 kam zyara 3a Le Charcutier
6. shtrit men Wooden Bakery mbere7 aktar men marra? adde bel zabt
7. kel ma na2asne shi benzal 3a Hibou, kam marra nezlet hal shaher
8. ma baddi adde dafa3et, bas kam marra re7et 3a O&C hal sene
9. 3a ases bas marra bel jemaa, kam marra re7et 3a Wooden Bakery ekher jem3ten
10. Le Charcutier men 1 la 15 teshreen el awal, kam marra shetrit men 3andon
11. 3a ases ma ba2a fout 3a Zara, kam marra rje3et re7et el shaher li mara2
12. 3ed kam marra akalet 3and Malak el Tawouk hal jemaa
13. kam marra re7na 3a burger house ekher 3 shhour

Labeling note: decided, T8 counts receipts (COUNT(DISTINCT receipt_id)), as the prompt and evaluation do.

## T9 Spending on an item
How much the user spent on one item, e.g. water, all time.

1. aday sarafet 3al may men awal ma ballashet sajjel masroufe
2. 7seble kel li dafa3to 3a 7alib men kel el fawatir
3. kel yom man2oushet zaatar, adde sarfet 3laya hal jemaa
4. jame3le taman kel 3elab el ton li shtarayton
5. ma baddi kel el snacks, bas el popcorn adde sarfet 3le hal shaher
6. el khobez li kel yom mn jibo, adde kallefna ekher shaher
7. 7seble masroufe 3a shampoo men awal el sene la halla2
8. baddi a3ref adde dafa3et 3a banadoura bi teshreen el awal
9. el croissant taba3 kel sobeh, chou tole3 majmou3o hal jemaa
10. 3tine total li sarafto 3a zeit zaytoun men kel el ma7allet
11. 3tine masroufe 3a digestive men kel el ma7allet li shetrit menna

## T10 An item of one brand
Spending on an item of a named brand, e.g. Barilla spaghetti.
  
1. aday sarafet 3a spaghetti Barilla hal shaher
2. 7seble kel li dafa3to 3a labnet Dairy Khoury
3. ktir hasse hale aam esrof 3a greek yoghurt taanayel
4. el chips taba3 Master adde kallefne hal jemaa
5. baddi total masroufe 3a hommos Al Wadi men awal el sene
6. ahwet Najjar la7ala adde sarfet 3laya bi ayloul
7. labne bas men Dairy Khoury, shu tole3 majmou3 li dafa3to ekher 3 shhour
8. adde ra7 men jaybte 3a terrea hal sayfiye
9. 7seble rimas brownies bi kel fawatire, men awal wa7de la ekher wa7de
10. shakle ma bekol ella Picon, adde dafa3et 3a jebneton hal shaher
11. ma baddi kel moshtarayete men Dairy Khoury, bas el labne adde tole3it 3laye
12. shu sarle def3a 3a bouzet Bonjus men awal el sayf la halla2
13. 7seble masroufe 3al nescafe bi teshreen el awal
14. el Pepsi la7alo adde kallefne hal shaher
15. adde dafa3et 3a jebnet Picon bi ayloul
16. shakle 3am beshteghil la eshrab Red Bull, adde sarfet 3le hal shaher
17. adde ra7 men jaybte 3a Nutella hal sene
18. shefle aday defaa ha2 terrea hal yawmein

## T11 Latest price
What the user paid for an item the last time, e.g. labneh.
  
1. adde dafa3et 7a2 el 3asal ekher marra
2. ekher marra jebt ma3joun snen Colgate, b adde ken
3. shu ken se3er kilo el moz bi ekher fetoura
4. el deodorant Nivea adde ekhado menne 7a2o ekher marra
5. nsit b adde jebt el 3adas, shouf ekher marra shtarayto
6. ekher 3elbet Kleenex adde kallefetne
7. baddi ekher se3er dafa3to 3a Ariel lal ghasil
8. ekher 3elbet Panadol jebta adde dafa3et 7a2a
9. adde kallefetne ekher pack fawet Always
10. el ketchup Heinz shu ken se3ro bi ekher fetoura
11. ekher marra shetrit pistachio, b adde ken el kilo
12. el 3elbet ma3moul li jebta ekher marra adde ken 7a2a
13. ja3 la ekher marra jebt fiya croissant w 2elle adde dafa3et 7a2o
14. khafet dekhan aday ken ha2a 3elbit el terrea ekher mara
15. shaklon ghalo el djej aday ken ha2o ekher mara shtrit

## T12 Average price
What the user usually pays for an item, e.g. eggs.
  
1. bel moyenne adde 3am edfa3 7a2 carton el bayd
2. el cappuccino adde 3am ykallefne bel motawassit
3. men kel el marraat li jebt fiya sokkar, adde ken se3er el kilo bel moyenne
4. shu average li dafa3to 3a 3elbet Feta hal shaher
5. bala ma te3tine kel fetoura la7ala, adde moyenne se3er el ice tea
6. el ka3ke b jebne, adde 3am totla3 3laye bel moyenne
7. kilo el kheyar adde 3am ykallefne 3adatan
8. shu average se3er 3elbet el baking powder bi fawatire
9. ma baddi arkh as se3er wala aghla se3er, baddi moyenne se3er el mozzarella li shtarayta
10. adde bel motawassit 3am edfa3 7a2 kilo el kafta
11. 7seble average se3er el sunscreen li bejibo
12. el digestive biscuits 3adatan b adde 3am jebon
13. men kel fawatire, shu moyenne li dafa3to 3a 3elbet laban 1 kilo

## T13 Price comparison between two shops
Which of two shops was cheaper for an item, e.g. rice at Happy or Carrefour.

1. 7a2 el Nutella li dafa3to bi Fahed a2al men Happy aw aktar
2. nafs 3elbet el Cheerios, wen dafa3et 7a2a a2al, bi Le Charcutier aw O&C
3. el 3asal bi Happy aw Fahed kallefne a2al
4. shouf fawatire men O&C w Le Charcutier, wen ken kilo el limoun arkhas
5. shetrit 3asir tiffe7 men Hibou w Happy, 3and min dafa3et a2al la nafs el litre
6. ben Maison M w Wooden Bakery, wen kallefetne man2oushet el jebne a2al
7. el Pampers nafs el size w 3adad el 7abbet, Happy aw Le Charcutier awfar 7asab li shtarayto
8. bi shbat, el frez jebto arkhas men Fahed aw Le Charcutier
9. el semsom men O&C talla3 3laye awfar men Le Charcutier aw la2
10. 7seble se3er el kilo lal jawz men Fahed w Happy w 2elle min ken arkhas
11. nafs charger Samsung, 3and min jebto arkhas, Khoury Home aw Abed Tahan
12. el mascara Maybelline nafsa, b ABC dafa3et aktar men Feel22?
13. 2arenle 7a2 rame el wara2 A4 ben Maliks w Librairie Antoine
14. shetrit nafs el Lego marrten, men JouéClub aw ABC ken awfar
15. el t-shirt el basic, Zara aw H&M kallefne a2al
16. ben Decathlon w Sports Experts, wen dafa3et a2al 7a2 yoga mat
17. el dafter A5 nafs 3adad el saf7at, Maliks aw Librairie Antoine ken arkhas
18. ma32oul dafa3et aktar 7a2 nafs el parfum bi ABC? 2arenle ma3 Feel22
19. 7seble se3er el 7abbe men akyes el zebbele li jebton men Fahed w O&C, aya awfar
20. nafs el kteb w nafs el edition, Librairie Antoine aw Maliks akhado menne a2al
21. el sneakers nafs el model, men ABC aw Sports Experts kenet el saf2a a7san 7asab li dafa3to

## T14 How many times an item was bought
How many times the user had or bought an item, e.g. manakish last month.
  
1. kam marra shtarayt man2oushe el shaher li mara2
2. baddi a3ref kam marra shtarayt cable lal telephone men awal el sene
3. ma baddi 3adad el 7abbet, baddi kam marra shtarayt batteries
4. 7asse kel shway bejib conditioner, kam marra shtarayto ekher 3 shhour
5. kam marra ken fi nail polish bi moshtarayete hal sene
6. el shawarma, kam marra talabet el jemaa li mar2it
7. shouf fawatire w 2elle kam marra jebt 3adas bi chbat
8. ma32oul rje3et shtarayt lip balm? kam marra jebto hal shaher
9. 3edde el marraat li shtarayt fiya ink lal printer
10. kam marra jebt chaussettes men awal el sene la halla2
11. baddi 3adad el marraat li shetrit fiya scented candles, mesh adde sarfet
12. el noodles hal shaher, kam marra jebt mennon
13. kam marra shtarayt akel lal bisse ekher 30 yom

## T15 How many of an item were bought
How many units the user bought, e.g. bottles of water this month.

1. 3eddele kel el pens li jebton hal sene
2. adde 3elbet tissues jebt ekher jem3ten
3. baddi 3adad el batteries li shtarayton, mesh kam marra shetrit
4. kam man2oushe talabna el jemaa li mar2it bel majmou3
5. 7asse 3ande ma7all candles, adde sham3a shtarayt men awal el sene
6. kam 3elbet contact lenses jebt ekher 6 shhour
7. jame3le 3adad el hangers li shtarayton men kel el fawatir
8. hal shaher kam 7abbet croissant jebt, mesh kam talab
9. adde rouleau wara2 toilette shtarayt bi chbat
10. kam daftar jebt men awal el sene la halla2
11. el packs taba3 el razors li shtarayton, kam shafra fiyon bel majmou3
12. kam 2anninet nail polish shtarayt hal sayfiye
13. kam kis akel lal besse jebt ekher 30 yom
14. aday jebet treats lal kaleb
15. kam t-shirt zedet 3al khezene el shaher li mara2
16. kam dazinet bayd jebt ekher jem3ten
17. kam litre benzin 3abbayt nhar el jem3a
18. kam rabtet khebez shtarayt hal jemaa
19. adde kilo la7me jebt bi nisen
20. kam rabtet ba2dounes jebt el jemaa li mar2it
21. kam kilo ghasil powder jebt ekher 3 shhour
22. 7seble kam gram loz shtarayt hal shaher
23. kam sandou2 may jebt men awal el shaher

## T16 Number of receipts
How many receipts the user has, e.g. from January.

1. kam fetoura 3ande men awal el sene la halla2
2. baddi a3ref kam receipt 3ande bel total
3. hal shaher kam fetoura sar 3ande
4. farjine 3adad el fawatir taba3 el shaher li mara2
5. kam fetoura 3ande tarikha mbere7
6. men 10 la 20 ayyar, adde fetoura 3ande
7. 7asse ma 3melt shi ella shopping, kam fetoura jama3et hal weekend
8. kam fetoura 3ande men Maliks hal sene
9. bi chbat la7alo kam receipt 3ande
10. adde sar 3ande fawatir men awal ma ballashet esta3mel el app
11. fawatir Abed Tahan hal sene, kam wa7de henne
12. kam fetoura 3ande la nhar 15 tamsmouz
13. 3eddele fawatir JouéClub men december
14. kel hal fawatir li 3ande, kam wa7de tole3o bel ekher

## T17 Comparing two months
Spending this month against last month, e.g. on groceries.

1. sarafet hal shaher aktar men el shaher li mara2 aw a2al
2. 2arenle masrouf el groceries hal shaher ma3 el shaher li ablo
3. adde el fare2 ben masroufe bi chbat w adar
4. el benzin kallefne aktar bi june aw july
5. 3tine total hal shaher w total el shaher li mara2 jamb ba3ed
6. masroufe 3al delivery zed aw na2as 3an el shaher li mara2? w b adde
7. aya shaher ba3za2et fi aktar, august aw september
8. 3a ases badde waffer, waffaret shi hal shaher 3an li ablo
9. 2arenle masroufe 3and Maliks hal shaher wel shaher li mara2
10. adde dafa3et 3a akel el bisse bi march w adde bi april
11. el ma7rou2at hal shaher nafs el masrouf ta2riban aw fi fare2 3an el shaher li ablo
12. baddi chouf iza masrouf el tyeb nezil men november la december
13. 7seble fare2 masrouf el bet ben ayyar w 7zayran

## F Follow-ups
Short questions that only make sense after an earlier one: change the period, the shop or the item, or narrow it
to one shop. Write the earlier question in brackets first, e.g. "(adde sraft 3al laban?) w el shaher el ablo?"

1. (aday sarafet hal shaher?) w el shaher li ablo?
2. (adde dafa3et 3al transport bi adar?) tab bi nisan?
3. (kam marra re7et 3a Maliks hal sene?) w Librairie Antoine?
4. (shu ekher se3er dafa3to 3a 3elbet tissues?) w abel hal marra?
5. (farjine masroufe 7asab el categories hal sene) nafs el shi bas la ekher jem3ten
6. (aya mahal sarfet fi aktar shi bi chbat?) w adde dafa3etlo?
7. (kam marra shtarayt candles hal shaher?) tayeb kam sham3a bel majmou3?
8. (adde sarfet bi O&C hal shaher?) 7awelle ye la dollar
9. (adde moyenne se3er kilo el frez?) bas men Fahed
10. (kam fetoura 3ande bi december?) adde mennon men JouéClub?
11. (aya aktar 3 categories sarfet 3layon hal shaher?) farjine 5 badal 3
12. (adde dafa3et 7a2 charger Samsung ekher marra?) men aya mahal jebto?
13. (adde sarfet 3al groceries hal jemaa?) men el tanayn lal jem3a bas
14. (2arenle se3er el Ariel ben Happy w Le Charcutier) nafs el comparison bas lal Persil
15. (adde dafa3et 3a akel el kaleb hal shaher?) w el treats la7alon?
16. (kam litre benzin 3abbayt hal shaher?) w adde kallefoune?
17. (aday tole3 aalaye mberha bi spinneys aal khodra?) aday 3al djej?

## C Clarify
Questions the assistant cannot answer without asking back: an item or shop the user doesn't have, or "the last
one" with nothing before it.
  
1. adde ken 7a2 ekher wa7ad
2. 7seble masroufe bi kanoun
3. adde dafa3et honik el jemaa li mar2it
4. el creme adde kallefetne
5. baddi total masroufe men wa2ta la halla2
6. shu se3er el 3elbe li jebta
7. adde sarfet bi mahal Ahmad
8. kam marra shtarayt heda
9. 7seble li dafa3to bi ekher fatra
10. el charger, taba3 el laptop aw el telephone ma betzakkar, adde ken
11. adde kenet ekher fetoura men nafs el mahal
12. kam marra re7et 3a Paul? ma ba3ref iza msajjal 3andak b esm tene
13. ma fhemet, fik tshra7a abssat?
14. la2 mesh hek azde
15. dekhan el iqos aday ken ha2o bi awalt el sene

## U Unsupported
Questions the receipts cannot answer: budgets, predictions, shop prices in general, advice, salary, other people.

1. b adde el iPhone halla2 bi kel el ma7allet
2. shu a7san laptop fine eshtri lal jem3a
3. adde ba2e bi 7sebe bel bank
4. eza baddalt sayarte, adde bwaffer benzin
5. el parfum li shtarayto original aw fake
6. fi stock men hal sneakers bi size 38?
7. talab el headphones wen sar
8. rje3le masari el dress li ma zabat
9. chou lezim wa2ef eshtri la waffer aktar
10. iza dallet hek, emta bekhlas ma3ashe
11. adde kelafit hal jacket el mahal abel ma ybi3ni yeha
12. leh el cashier 7asabne hek, ken 3am ygheshne?
13. shu kenit refi2te sherye mbere7
  

## R Replies
Greetings, thanks, "what can you do", small talk.

1. bonjour (lebanese reply is usually bonjourein)
2. sabah el kheir
3. shu fik tse3edne
4. shu fine es2alak 3an fawatire
5. fik tefham aalaye aw ektob english?
6. teslam, hayda li ken badde ye
7. eh hek tamam
8. perfect thank you
9. wow ma kent metwa23a
10. ya wayle 3a hal masrouf
11. khalas bala ma tfajja3ne aktar
12. 3am bemza7 ma3ak
13. nharak sa3id 
14. sabah el wared
15. shlonak
16. shu btaamel/btaamol/bta3mol
17. khaberne aanak


---

## Arabizi words
How people write each item or category. Add any you know, and add items that are missing.

Food and drinks
- water: may, mayy, mai, mayye
- rice: rez, rezz, roz, ruz
- chicken: djej, djeij, djaaj, jaj, dajaj
- whole chicken: farrouj, farouj, farooj
- tawouk: tawouk, taouk, tawook
- shawarma: shawarma, chawarma, shawerma
- meat: la7me, la7meh, lahme, lahmeh
- minced meat: la7me mafroume, lahme mafrume
- kafta: kafta, kefta
- fish: samak, samak fresh
- tuna: ton, toun, tuna
- manakish: mana2ish, man2ish, manakish, mana2eesh
- manoushe: man2oushe, man2ouche, man2ushe, manoushe
- zaatar: zaatar, za3tar, za3ter
- laban: laban
- labneh: labne, labneh, lebne
- cheese: jebne, jebneh, jibne
- halloumi: 7alloum, halloum, 7aloum, halloumi
- eggs: bayd, beyd, beid
- bread: khebez, khobez, khobz, 5obez, 5ebez
- milk: 7alib, 7aleeb, halib
- coffee: ahwe, 2ahwe, ahweh, kahwe
- tea: shay, chai, chay, shey
- sugar: sekkar, sokkar, soukkar, sukkar
- salt: mele7, meleh, mel7
- flour: t7in, ta7in, ta7ine
- tahini: t7ine, ta7ine, tahine, tahini
- oil: zeit, zayt, zet
- olive oil: zeit zaytoun, zet zeytoun, zeit zeitoun
- butter: zebde, zibde, zebdeh
- ghee: samne, samneh
- lentils: 3adas, adas
- chickpeas: 7ommos 7ab, hommos hab, 7ommos yebis
- hummus dip: hommos bi t7ine, 7ommos b ta7ine, hummus
- beans: fasoulya, fasolia, fasoulia
- foul: foul, ful, fool
- pasta: ma3karona, makarona, macarona, pasta
- vermicelli: sh3ayriye, sha3riye, cha3riye
- potatoes: batata, batatit
- tomatoes: banadoura, banadora, bandora
- cucumber: kheyar, 5yar, khyar
- onion: basal, bassal
- garlic: toum, toom, tum
- lettuce: khass, khas, 5ass
- carrots: jazar
- zucchini: kousa, kusa, koosa
- eggplant: batenjen, batenjan, batinjen
- lemon: 7amod, 7amoud, hamod
- oranges: bourtou2an, borto2an, burtu2an
- apples: teffe7, tiffe7, teffeh, tuffe7
- bananas: moz, mouz, mooz
- strawberries: frez, fraise
- grapes: 3inab, 3enab, enab
- watermelon: battikh, batikh, batteekh
- parsley: ba2dounes, ba2dounis, ba2dones
- mint: na3na3, naanaa, na3na
- nuts: mkassarat, moukassarat, mkasarat
- almonds: loz, looz, lawz
- walnuts: jawz, joz
- pistachios: fosto2, festo2, fustok
- honey: 3asal, asal
- jam: mrabba, mrabbah
- biscuits: baskawit, baskot, biscuit, biscuits
- chocolate: shokolata, chocolata, chocolate
- ice cream: bouza, booza, buza
- juice: 3asir, 3aseer, jus
- chewing gum: 3elke, 3ilke, 3elka
- sweets: 7elo, 7elw, 7alawiyet, 7alaweyet
- cake: gateau, gato, cake, kek
- croissant: croissant, croissan, krwason
Household and personal care
- soap: saboun, sabon, savon
- shampoo: shampoo, shampo, champo, champoo
- conditioner: conditioner, apres shampoing, balsam
- toothpaste: ma3joun snen, ma3jun snan, toothpaste
- toothbrush: ferchet snen, fershet snan, toothbrush
- deodorant: deodorant, deo, mouzil 3ara2
- sunscreen: sunscreen, sunblock, creme solaire, we2e shams
- moisturizer: moisturizer, creme hydratante, krem tartib
- perfume: parfum, perfume, 3eter, 3itr
- tissues: kleenex, klinex, tissues, wara2 ma7arem
- toilet paper: wara2 toilette, wara2 toilet, toilet paper
- pads: fowat so7iye, fawet se7iye, pads, serviettes hygieniques
- diapers: 7afadat, 7affadat, diapers, couches
- laundry detergent: mas7ou2 ghasil, poudre ghasil, laundry detergent
- dishwashing liquid: sabon jale, savon jale, seyel jale
- sponge: safra jale, sponge, esfenje
- bleach: javel, javelle, klor, chlorine
- garbage bags: kyess zbele, akyes zebbele, garbage bags
- candles: sham3, cham3, sham3a
- batteries: battariyet, batariyet, batteries, piles
- light bulb: lambe, lamba, light bulb
- towels: manashif, manachif, manshafe
- sheets: sharashif, charachif, sharshaf
- hangers: 3alla2at, 3ala2at, hangers
Clothes, electronics, and other items
- clothes: tyeb, tiyeb, tyab, clothes
- trousers: bantalon, pantalon, pantaloun
- shirt: 2amis, amis, chemise
- T-shirt: tshirt, t-shirt, t shirt
- shoes: sabbat, sabat, shoes
- socks: kalsat, kalset, chaussettes, socks
- jacket: jacket, jaket, blouson
- bag: shanta, chanta, bag
- wallet: ma7faza, portefeuille, wallet
- glasses: naddarat, nadarat, nazzarat
- charger: charger, chargeur, sherjer, sha7en
- cable: cable, kabel, kebel
- headphones: headphones, casque, samme3at, sama3at
- phone case: cover, phone case, coque, cover telephone
- screen protector: screen protector, protection ecran, screen protection
- mouse: mouse, souris, maws
- keyboard: keyboard, clavier
- notebook: daftar, dafter, cahier
- pen: 2alam, alam, stylo
- book: kteb, kitab, ktab
- printer ink: 7ebr, 7iber, ink, encre
- cat food: akel lal besse, akel bses, cat food
- dog food: akel lal kaleb, akel kleb, dog food
Category wording and related search terms
- Transport: na2el, mouwasalet, transport
  Related: taxi, taksi, service, servicet, servis, uber, bolt, benzin, benzine, parking
- Groceries: groceries, ma2ade, ma2adi, aghrad el bet, ghrad el bait, moshtarayet supermarket
- Dining: akel barra, akel bara, mata3em, mat3am, resto, restaurant
- Delivery: delivery, talabet akel, akel delivery
- Health: se77a, so7a, health
  Related: dawa, adwiye, edewye, saydaliye, saydaliyye, 2edwiti
- Clothing: tyeb, malebis, clothes, clothing, 
- Beauty: beauty, tajmil, makeup, maquillage, skincare
- Household: aghrad el bet, ghrad el bait, eshya lal bayt, mostalzamat el bet, household
- Cleaning: tandif, tanzif, tondif, cleaning, mawed tandif
- Education: ta3lim, te3lim, derase, dirase, education
- Stationery: 2artasiye, kartasiye, stationery, aghrad madrase, kortasie
- Electronics: electronics, electroniques, ajhize electroniye
- Entertainment: tarfih, entertainment, cinema, games,
- Gifts: hadeye, hadaya, hdaya, gifts
- Pets: pets, 7ayawanet alife, aghrad el bses, aghrad el kleb
- Subscriptions: eshtiraket, ishtirakat, subscriptions, abonnements
- Repairs: tasli7, tesli7, maintenance, siyene, siyane
- Tobacco: dekhan, dokhan, cigarettes, sigarat
Money and receipt vocabulary
- money: masare, masari, masareh, mosriyet, masriyet
- my money: masriyete, mosriyete, masreyete
- spending: masrouf, masroof, saref, sarf
- I spent: sarafet, sarafit, sarfet, saraft
- I paid: dafa3et, dafa3t, def3et, dafaat
- price: se3er, se3r, si3er, 7a2, ha2
- receipt: fetoura, fatoura, fetura, receipt, ticket
- receipts: fawatir, fwetir, fawetir, receipts
- total: majmou3, majmu3, total
- average: moyenne, average, motawassit, metwasset
- cheaper: arkhas, ar5as, awfar
- more expensive: aghla, a8la
- how much: aday, adde, ade, adday, adaysh, addech
- how many times: kam marra, adde marra, kam mara
- bought: shtarayt, shtarit, shtrit, shetrit, chtarit
- splurged: ba3za2et, ba3za2t, ba3za2it, baaza2et
Quantities and units
- piece: 7abbe, habbe, 2et3a, piece
- box: 3elbe, 3elbeh, 3ilbe, box
- bag: kis, kees
- pack: pack, paquet, pake
- bottle: 2annine, annine, 2enine
- carton: carton, karton, kartoun
- dozen: dazine, dazzine, dozen
- half a dozen: noss dazine, nos dazine
- pair: jawz, joz, pair
- kilo: kilo, kilou, kg
- gram: gram, ghram, gr
- litre: litre, liter, litr
- roll: rouleau, rolo, roll
- bundle: rabta, rabtet, rabte
- can: 3elbet, can, tin
Days and periods
- Monday: tanayn, tanain, tnen, tnein, etnen
- Tuesday: taleta, tleeta, tleta
- Wednesday: erb3a, orb3a, erbaa, arbi3a
- Thursday: khamis, 5amis, khamees
- Friday: jem3a, jemaa, jom3a, joum3a
- Saturday: sabet, sebet, sabt
- Sunday: a7ad, ahad, el a7ad
- today: lyom, lyoum, el yom
- yesterday: mbere7, mberi7, mbereh
- day before yesterday: awal mbere7, awwal mbere7, awalt mbereh,
- week: jem3a, jemaa, osbou3, esbou3, jom3a
- month: shaher, chaher, shahr
- year: sene, seneh, sana
- last: ekher, ekhir, li mara2, li mar2it, li ata3
- since: men, mn, men wa2t
- until now: la halla2, la hala2, lahalla2, la hadit halae.
Tobacco product names
- IQOS device: iqos, ikos, aykos
- TEREA tobacco sticks: terea, terrea, teria
- HEETS tobacco sticks: heets, hits, heats
Matching notes: jem3a can mean Friday or week; jawz can mean walnuts or a pair; ta7ine can be ambiguous between flour and tahini. Brand names used generically—such as Kleenex for tissues—also need context.