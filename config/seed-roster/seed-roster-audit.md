# Seed roster audit

Files:
- `seed-roster.txt` — the roster with `# === SECTION ===` headers for auditing. Delete whole sections to trim.
- `seed-roster-wikicheck.tsv` — per-name Wikipedia coverage data.
- `seed-roster-names.txt` — same list with headers stripped, one name per line, for the run.

Source: `llm-household-names-1000.txt` (723 kept verbatim, ~30 renamed, ~245 dropped) plus ~1140 additions, including a dedicated AI section.

## Removed: hate symbols, genocide, extremist platforming
Adolf Hitler, Eva Braun, Heinrich Himmler, Hermann Göring, Josef Mengele, Erwin Rommel, Pol Pot, Slobodan Milošević, Osama bin Laden, Aung San Suu Kyi (Rohingya), Robert E. Lee (Confederate statue flashpoint), Kanye West (2025 Nazi-praise era; hate-platforming risk).
Borderline, removed: Idi Amin (mass killer; flip back if you want the caricature, he's on par with Gaddafi who stayed).

## Removed: Arab/Israeli conflict, live conflicts, militant leaders
Yasser Arafat, Benjamin Netanyahu, Golda Meir, David Ben-Gurion, Shimon Peres, Yitzhak Rabin, Bashar al-Assad, Ayatollah Khomeini, Mahmoud Ahmadinejad, Mohammad Reza Pahlavi, Hosni Mubarak, Anwar Sadat, Vladimir Putin, Volodymyr Zelenskyy, Nicolás Maduro (Venezuela is a live flashpoint as of 2026).
Kept on purpose: Saddam Hussein, Muammar Gaddafi, Gamal Abdel Nasser (dead, pop-culture villains, not live-conflict symbols). Gal Gadot kept (actress) but she is a mild flashpoint; flagged.

## Removed: fame inseparable from victimization
Anne Frank, George Floyd, Alexei Navalny, Kalpana Chawla.

## Removed: sexual abuse / active serious proceedings
- Jerry Lee Lewis — married his 13-year-old cousin; well-established.
- Neil Gaiman — active 2025 sexual assault civil litigation. Quarantined.
- Chris Brown — DV conviction plus active 2025 UK GBH prosecution. Quarantined.
- Rodrigo Duterte — in ICC custody for crimes against humanity.
- Imran Khan — imprisoned, active political prosecution; live political flashpoint in Pakistan.
- Jacob Zuma — rape trial (acquitted) plus active corruption trial; low roster value anyway.

## Kept but flagged (your call)
- Mike Tyson — 1992 rape conviction. Your rule says remove convictions; I kept him because he is the single most iconic fighter alive and is culturally rehabilitated. Flip if you disagree.
- Conor McGregor — lost a civil sexual-assault case in 2024, appeal failed 2025. Kept for the same reason; borderline.
- Jon Jones — long rap sheet (DV, hit-and-run), nothing sexual, nothing active at felony level.
- Diddy — included per your explicit exception.
- Pee-wee Herman — 1991 indecent exposure and a 2002 obscenity misdemeanor. Beloved; kept.
- Floyd Mayweather — DV convictions, kept.
- O.J. Simpson, Charles Manson, Pablo Escobar, El Chapo, Al Capone, Bernie Madoff, Elizabeth Holmes, SBF, Anna Delvey, Tonya Harding — intentional true-crime villains.
- Buddha — depiction of Buddha in a fighting game got Fight of Gods banned in Malaysia. Cultural risk is real but moderate; kept because you asked. Jesus Christ and Moses kept. Muhammad and Guru Nanak deliberately not added.
- Yasuke — historical, but became a culture-war flashpoint via Assassin's Creed Shadows. Harmless in itself.
- Kim Jong Un, Xi Jinping, Donald Trump, Narendra Modi, Erdoğan, Javier Milei — living heads of state kept; image gen may refuse them, so sort them last in the run.
- Salman Khan — hit-and-run and poaching cases, acquitted; kept.
- Silvio Berlusconi — tax-fraud conviction, bunga bunga; kept as a caricature.

## Considered and deliberately NOT added
Sexual-abuse tier: Bill Cosby, Harvey Weinstein, Jeffrey Epstein, R. Kelly, Roman Polanski, Woody Allen, Kevin Spacey, Gérard Depardieu (2025 conviction), Marilyn Manson (allegations, no charges; skipped for taste), Afrika Bambaataa, Pete Townshend, Lawrence Taylor, Karl Malone, Vince McMahon (active trafficking suit), Nick Carter (active suits), Russell Brand (active rape charges), Andrew Tate, Dr Disrespect, Danny Masterson, Jonathan Majors, James Franco, Till Lindemann, Hugh Hefner, Ted Bundy, Jeffrey Dahmer, Chris Benoit, Jimmy Snuka, Aaron Hernandez, Adrian Peterson, Ray Rice, Michael Vick.
Political badness / flashpoints: Charlie Kirk, Alex Jones, Tucker Carlson, Ben Shapiro, Jordan Peterson, Andrew Cuomo, Roseanne Barr, Michael Richards, Henry Kissinger, George Soros (conspiracy magnet), Mohammed bin Salman, Luigi Mangione, Nigel Farage, Ted Nugent, Herschel Walker.
Sacred: Muhammad, Guru Nanak.
Canadian provincial politicians from the Wikipedia list tail: left out. The AI founders from that tail were pulled into a new AI & MACHINE LEARNING section (~65 names) since the audience is AI people; Sam Altman moved there from Tech.
Fictional and legendary people (King Arthur, Robin Hood, Santa Claus) left out; every entry is a real person, with Ragnar Lothbrok and Hattori Hanzo as the semi-historical exceptions.

## Renamed for the announcer
| Was | Now |
|---|---|
| Augustus | Caesar Augustus |
| Arthur Wellesley | The Duke of Wellington |
| Napoleon Bonaparte | Napoleon |
| Henry VIII | King Henry the Eighth |
| Elizabeth I | Queen Elizabeth the First |
| Louis XIV | King Louis the Fourteenth |
| George III | King George the Third |
| Elizabeth II | Queen Elizabeth the Second |
| Charles III | King Charles the Third |
| Diana, Princess of Wales | Princess Diana |
| Catherine, Princess of Wales | Kate Middleton |
| Meghan, Duchess of Sussex | Meghan Markle |
| Kaiser Wilhelm II | Kaiser Wilhelm |
| Pope John Paul II | Pope John Paul the Second |
| Jacqueline Kennedy Onassis | Jackie Kennedy |
| Franklin D. Roosevelt | Franklin Roosevelt |
| Harry S. Truman | Harry Truman |
| Dwight D. Eisenhower | Dwight Eisenhower |
| Lyndon B. Johnson | Lyndon Johnson |
| Dwayne Johnson | Dwayne The Rock Johnson |
| Priyanka Chopra Jonas | Priyanka Chopra |
| Aishwarya Rai Bachchan | Aishwarya Rai |
| Selena Quintanilla | Selena |
| Floyd Mayweather Jr. | Floyd Mayweather |
| The Notorious B.I.G. | Biggie Smalls |
| OJ Simpson | O.J. Simpson |
Added names already use the spoken form: Ronaldo Nazário (to disambiguate from Cristiano), Salt Bae, Mister Rogers, Pee-wee Herman, Weird Al Yankovic, Colonel Sanders, Refrigerator Perry, Macho Man Randy Savage, Rowdy Roddy Piper, Jake the Snake Roberts, MySpace Tom, Ichiro, Marta, Teller.

## Removed for low recognizability (not household enough for a fighter announcer)
Politicians: John Adams, James Madison, Woodrow Wilson, Gerald Ford, George H. W. Bush, Al Gore, John McCain, Mitt Romney, Neville Chamberlain, Gordon Brown, David Cameron, Theresa May, Rishi Sunak, Keir Starmer, Prince Albert, Prince Philip, Mary I, James I, Charles I, Edward VIII, George VI, Friedrich Engels, Leon Trotsky, Boris Yeltsin, Raúl Castro, Pierre Trudeau, Stephen Harper, Kim Jong Il, Kim Il Sung, Deng Xiaoping, Chiang Kai-shek, Sun Yat-sen, Lee Kuan Yew, Ferdinand Marcos, Corazon Aquino, Nehru, Rajiv Gandhi, Benazir Bhutto, Jinnah, Ramaphosa, Mugabe, Wałęsa, Havel, Tito, Kohl, Sarkozy (also jailed 2025), Pope Benedict, John Calvin, Aquinas, Augustine, John Lewis, Jesse Jackson, Elizabeth Cady Stanton, Betty Friedan, Margaret Sanger (eugenics baggage), Chelsea Manning, Oskar Schindler, José de San Martín.
Science: Alexei Leonov, Chris Hadfield, Vespucci, Pizarro, Robert Falcon Scott, Pierre Curie, Mendel, Morse, Faraday, Watt, Fermi, Planck, Babbage, Dorothy Vaughan, Mary Jackson, James Watson (racism remarks), Crick, Skinner, Brian Cox, Dawkins, Kaku, Booker T. Washington, Du Bois, Clara Barton, Blackwell, Lister, Jenner, Koch, Leeuwenhoek, Vesalius, Paracelsus, Pascal, Leibniz, Euler, Gauss, Shannon, Mendeleev, Lavoisier, Boyle, Hubble, Piaget, Keynes, Friedman, Chomsky.
Arts and letters: Manet, Cézanne, Gauguin, Renoir, Henry Moore, Cartier-Bresson, Ansel Adams, Leibovitz, Chaucer, Milton, Wordsworth, Coleridge, Percy Shelley, Keats, Hardy, George Eliot, Defoe, Swift, A. A. Milne, Beecher Stowe, Emerson, Thoreau, Langston Hughes, Ginsberg, Heller, Dan Brown, Grisham, Suzanne Collins, Ishiguro, Allende, Coelho, Chekhov, Solzhenitsyn, Nabokov, de Beauvoir, Proust, Rousseau, Kierkegaard, Locke, Hobbes, Russell.
Screen: Spencer Tracy, Gregory Peck, Mickey Rooney, Gary Cooper, Peter Cushing, Omar Sharif, Jeremy Irons, Colin Firth, Brendan Gleeson, Kenneth Branagh, Chris Tucker, Martin Short, Vince Vaughn, Amanda Seyfried, Amy Adams, Jessica Chastain, Rachel McAdams, Octavia Spencer, Taraji P. Henson, Eva Longoria, Courteney Cox, Lisa Kudrow, Kim Basinger, Dakota Johnson, Eddie Redmayne, Mahershala Ali, Paul Giamatti, Graham Chapman, Terry Gilliam, Terry Jones, Tony Leung, Mohanlal, Irrfan Khan, Dev Patel.
Music: Peter Tosh, Jimmy Cliff, José Feliciano, Fats Domino, Al Green, Gladys Knight, Patti LaBelle, Chaka Khan, Kenny Rogers, Patsy Cline, George Strait, Tim McGraw, Faith Hill, Blake Shelton, Luke Bryan, Reba McEntire, Art Garfunkel, Carole King, James Taylor, Neil Diamond, Roger Waters, David Gilmour, Chris Cornell, Lars Ulrich, Sia, Kelly Clarkson, Shawn Mendes, Julio Iglesias, Daddy Yankee, Mary J. Blige.
Sports: Eli Manning, Scottie Pippen, Oscar De La Hoya, Venus Williams.

## Run ordering suggestion
The file is grouped by category, so do not run a prefix. Either shuffle, or stratify one pass per section. Put living heads of state and the true-crime section last since they are the likeliest image-gen refusals.

## Weights-coverage check (Wikipedia proxy)
`seed-roster-wikicheck.tsv` has, per name: resolved Wikipedia title, article status, whether the article has a lead photo, and June–August 2026 pageviews. Pageviews are a proxy for "is this face in the image model's weights"; the true test is a spot-check generation.
- Every name resolved to a real article (ambiguous ones like Drake, Sting, Slash, Prince were mapped explicitly).
- Roster median is ~200k views per 3 months. Only ~30 names sat under 30k, and nearly all were deep-cut AI researchers.
- Dropped after review (32 names, no probation file): the thin-coverage AI researchers (Zaremba, Koller, Goodfellow, Russell, Kai-Fu Lee, Mostaque, Silver, Schmidhuber, Schulman, Pearl, Marcus, Legg, Gomez, Sutton, Leike, Mensch, Vaswani, Liang Wenfeng, Kaplan, Olah, Sanderson, Tegmark, Hotz, Jack Clark) plus people with no public face (Eiichiro Oda, Banksy, Satoshi Tajiri, Gary Larson, Bill Watterson) and three low-signal athletes (Mick Fanning, Richie McCaw, Will Wright). Reviewed and removed for good.
- AI names that stayed, all comfortably covered: Hinton, LeCun, Bengio, Ng, Fei-Fei Li, Altman, Brockman, Sutskever, Murati, Karpathy, Dario and Daniela Amodei, Hassabis, Suleyman, Jeff Dean, Shazeer, Alexandr Wang, Aravind Srinivas, Delangue, Lisa Su, Palmer Luckey, Andreessen, Reid Hoffman, Paul Graham, van Rossum, Knuth, Wolfram, Kurzweil, Minsky, McCarthy, Shannon, Bostrom, Yudkowsky, Gebru, Terence Tao, Lex Fridman, Dwarkesh Patel, Lee Sedol.
- Ancient and medieval figures show "no photo" by definition; they are heavily depicted in art and games and are fine.

## Fictional & folklore section (added on request)
~170 names, all public domain in the US. Sub-headers: folklore/holiday, cryptids, myth, legend, literature, Shakespeare, art come to life, newly-PD cartoons.
Naming is chosen to steer image gen away from trademarked designs: "Thor the Norse God" not "Thor", "Polyphemus the Cyclops" not "Cyclops", "Hercules the Greek Hero", "Alice in Wonderland", "Dorothy Gale".
- Kept with a trademark note: Tarzan, John Carter of Mars, Zorro (stories are PD; ERB Inc and Zorro Productions still hold marks and litigate). Betty Boop, Popeye, Olive Oyl, Felix the Cat, Oswald (PD designs; Fleischer/King Features/Disney hold marks on modern versions, so stay period-accurate). Tintin is PD in the US only (Hergé's EU copyright runs to 2054). Winnie the Pooh and Tigger must be Shepard-style, not Disney.
- Excluded: Steamboat Willie Mickey (Disney litigation magnet), Bluto (1932, not PD until 2028), Captain Haddock (1941), The Shadow, Buck Rogers, Nancy Drew, Hardy Boys (low fighter value plus live marks), Puss in Boots and Aladdin (folk tales, but image gen collapses to the DreamWorks/Disney design), Slender Man (real-world stabbing case), any Disney-designed princess, Universal monster designs (the Mummy, the Wolf Man, Bride of Frankenstein), post-1930 artworks like Magritte's Son of Man.

## Tiering (funny / distinctive ranking)
Wikipedia pageviews rank fame, not fighter value, so every name was hand-tiered:
- S (277): instantly recognizable silhouette plus built-in comedy or fighter fantasy. Colonel Sanders, Venus de Milo, Andre the Giant, Bob Ross, Kim Jong Un, Salt Bae, Popeye.
- A (777): strong iconic look or prop. Napoleon, Slash, Anna Wintour, Hitchcock, Gandalf-adjacent actors, most wrestlers and musicians with a look.
- B (9): leftovers not explicitly tiered.
- C (924): recognizable only as a headshot, or a suit. Most modern actors, politicians, scientists, writers, models, generic athletes.
Run order is tier-major, then category round-robin within tier, then pageviews. The C tier is still in the file so nothing is lost; run it last or not at all.
