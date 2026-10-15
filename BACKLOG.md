# Backlog

Planned work, not implemented behavior. Each item requires separate implementation
and verification. Item numbers are stable references, not execution priority.
Recommended execution order:

1. [Verify the implemented test baseline in the lab (item 10)](#10-supplement-test-coverage-before-structural-changes).
2. [Rename core to platform (item 8)](#8-rename-core-to-platform).
3. [Extract Identity (item 9)](#9-extract-identity-into-a-separate-component-and-bundle).
4. [Deploy maintainability refactor (item 1)](#1-deploy-maintainability-refactor).

The full agent task descriptions for items 8, 9 and 10 are preserved below, with
heading levels adjusted for this document. The later clarification in item 9
supersedes item 8's bundled-platform assumptions: platform is to be a separate
bundle with explicit dependencies, and app bundles must not embed it. Do not
reintroduce the older bundle model while renaming. Inspect the actual repository
baseline before implementation; these tasks are not claims of completed work.

The refactor must preserve the behavior and naming established by items 8 and 9;
its original core terminology below is historical scope, not an instruction to
restore core or merge Identity back into platform.

## 10. Supplement test coverage before structural changes

Status: implemented locally; historical lab verification pending, before items 8, 9 and 1.
See [test baseline and lab command](acceptance/TEST-BASELINE.md) for coverage,
results and the retained 0.2.0 upgrade gate. The original task is preserved below.
This task includes the retained 0.2.0 upgrade scenario already tracked in item 5;
implement it once and cross-reference its evidence rather than duplicating it.

Suppler testdekningen i `gunstein/podman_offline` før den planlagte refaktoreringen av deploy-koden.

Målet er å etablere en tydelig, testet baseline for eksisterende oppførsel. Dette er en avgrenset testoppgave, ikke selve refaktoreringen.

### 1. Kartlegg eksisterende dekning og kjør baseline

Les dagens kode, tester og verifikasjonsrapporter. Kontroller særlig:

- `tests/`
- `acceptance/`
- `deploy.py`
- `bundle.py`
- Rotkommandoene og bundle-innholdet.

Kjør eksisterende produkt- og acceptance-harness-tester før endringer. Registrer commit og resultater.

Gjenbruk eksisterende fixtures og testverktøy. Ikke dupliser tester som allerede dekker kravene nedenfor.

### 2. Test reell oppgradering fra 0.2.0

Legg til et målrettet acceptance-scenario som oppgraderer en faktisk 0.2.0-installasjon til dagens versjon.

Bruk en identifisert historisk commit for gammel kode og gamle images. Ikke simuler gammel release ved bare å endre `VERSION` i dagens kode.

Scenario:

1. Bygg og installer gammel app1/core og app2.
2. Opprett brukerdata gjennom eksisterende e2e-/markørmekanisme.
3. Registrer eksisterende versjoner, config, credential-filer, databasevolumer og relevante tjenesteobservasjoner.
4. Følg dagens dokumenterte manuelle oppgraderingssteg: legg til nødvendige DB-felter og `GENERATED_SECRETS`-oppføringer i persistent config.
5. Overfør og installer ny app1/core-bundle.
6. Verifiser at app1/core fungerer, og at gammel app2 fortsatt fungerer uten utilsiktede endringer.
7. Oppgrader deretter app2 og verifiser hele installasjonen.

Kontroller spesielt:

- Eksisterende databasepassord beholdes byte-for-byte.
- Databasevolumer beholdes, og eksisterende brukerdata er tilgjengelige.
- Persistent config endres bare gjennom de eksplisitte operatørstegene.
- Ingen credentials regenereres eller databasebrukere endres automatisk.
- App1-oppgraderingen ikke endrer app2s tjeneste, versjon, config eller credentials.
- Innlogging og databaseoperasjoner fungerer etter hvert oppgraderingstrinn.
- Trust for gammel release fjernes først etter vellykket verifikasjon, uten å berøre sibling-bundles.

Test også at manglende nødvendige configtillegg avvises før image-operasjoner og endringer i installert tilstand. Dette kan dekkes av en fokusert lokal test dersom eksisterende dekning er tilstrekkelig.

Hold scenarioet avgrenset. Ikke gjenta hele matrisen av reboot-, crash- og hang-tester hvis disse allerede dekkes separat.

### 3. Lås feiloppførselen under installasjon

Undersøk eksisterende dekning og suppler for:

- Feil under `podman load`.
- Feil eller manglende image ved `podman image exists`.
- Feil ved restart eller `is-active` for en berørt systemd-tjeneste.

Bruk eksisterende komponentinstallasjon som utgangspunkt.

Test relevante observasjoner:

- Persistent config og credentials.
- Importarkiver.
- Route- og OIDC-klientregistreringer.
- Quadlet- og YAML-filer.
- Versjonsmarkører.
- Hvilke tjenester som er forsøkt restartet, og i hvilken rekkefølge.
- At upåvirkede sibling-komponenter beholdes.

Skille mellom feil før og etter at installasjonen begynner å endre tilstand. Ikke anta at installasjon er atomisk eller at rollback allerede finnes.

Ved servicefeil skal testen beskrive den faktiske delvis gjennomførte tilstanden og kontrollere at videre steg stopper, og at versjonsmarkører ikke feilaktig hevder en fullført installasjon.

Bruk konkrete feilscenarioer fremfor tester som bare gjentar interne funksjonskall.

Hvis du finner en eksisterende feil, dokumenter den med en fokusert reproduksjon. Ikke lås en kjent feil som ønsket oppførsel eller gjør urelaterte produktendringer uten å synliggjøre dem.

### 4. Test rotkommandoer fra en annen arbeidsmappe

Legg til integrasjonstester som starter de faktiske wrapper-scriptene fra en arbeidsmappe utenfor checkout/release:

```text
./deploy prepare
./deploy init-config <component>
./deploy install
./deploy uninstall
./build-bundle.sh
```

Bruk absolutt sti til wrapperen i testen.

Test kommandoene i riktig kontekst:

- `prepare` og bundling fra kildekoden.
- `init-config`, `install` og `uninstall` fra en utpakket bundle.

Verifiser at ressursstier og configvalg fungerer uavhengig av callerens arbeidsmappe, og at output ikke utilsiktet skrives dit.

Bruk isolerte midlertidige mapper og eksisterende stubs for Podman/systemd der det er hensiktsmessig. Ikke kjør produksjonskommandoer mot utviklerens virkelige hjem eller containermiljø.

Der realistisk testing krever tjenestebruker, brukerhjem og systemd-runtime, legg kontrollen i det eksisterende autoriserte labscenarioet fremfor å bygge et komplisert nytt mock-rammeverk.

### 5. Avgrensning

Ikke implementer:

- Oppdeling i `deployment/`-pakken.
- Ny CLI-arkitektur.
- Directory trust for fapolicyd.
- Passordrotasjon.
- Automatisk config- eller databasemigrering.
- Ny rollback-mekanisme.

Tester for den kommende pakkestrukturen, `python -B`, bytecode-ekskludering og directory trust hører til refaktoreringsoppgaven.

Behold eksisterende sikkerhetskontroller og testassertions. Ikke svekk dem for å få nye scenarioer til å passere.

### 6. Verifikasjon

Kjør etter endringene:

- Alle produkttester.
- Alle acceptance-harness-tester.
- Relevante ruff-, format-, pyright-, vermin- og shellcheck-kontroller med prosjektets eksisterende oppsett.

Behold Python 3.6-kompatibilitet for host-verktøy og produkttester.

Kjør det nye reelle oppgraderingsscenarioet dersom det etablerte labmiljøet er tilgjengelig og kjøring er autorisert. Ikke reset eller endre andre miljøer.

Skill tydelig mellom lokale tester, harness-tester og faktiske målmaskinkjøringer. Hvis labkjøring ikke er mulig, implementer scenarioet og rapporter at oppgraderingen fortsatt ikke er operasjonelt verifisert.

### 7. Leveranse

Rapporter kort:

1. Baseline-commit og testresultater før endringer.
2. Hvilken dekning som allerede fantes.
3. Nye tester og hvilke konkrete feil de beskytter mot.
4. Historisk og ny revision brukt i upgrade-scenarioet.
5. Testresultater, inkludert faktisk labkjøring.
6. Eventuelle oppdagede produktfeil og verifikasjonshull.
7. Om baseline er tilstrekkelig til å starte refaktoreringen.

Oppdater relevant testdokumentasjon med garantiene og begrensningene.

Foretrekk noen få sterke tester fremfor mange overlappende tester.

## 1. Deploy maintainability refactor

Status: planned; after items 10, 8 and 9.

Refactor the deploy implementation for maintainability without redesigning the architecture or changing behavior.

Goal: a medium-experienced developer with some Python knowledge and little familiarity with this project should be able to understand the install/upgrade/uninstall flow quickly.

Keep the root commands unchanged:

- `./deploy prepare`
- `./deploy install`
- `./deploy uninstall`
- `./build-bundle.sh`

Move deploy internals into a small Python package, roughly:

```text
deployment/
  __init__.py
  __main__.py
  cli.py
  deploy.py
  render.py
```

Keep `./deploy` as the stable entrypoint and run Python with `-B`, e.g. `python3 -B -m deployment`, so trusted release code does not create `.pyc`/`__pycache__`. Preserve invocation from outside the release directory as well.

Responsibilities:

- `render.py`: config/YAML loading, placeholders, generated-secret helpers, SECRET_FILES/VOLUME_FILES, Secret/PVC generation, manifest validation/rendering.
- `deploy.py`: production environment, component/bundle selection, VERSION/CORE_VERSION logic, registrations/routes/OIDC clients, image load/verify, Quadlet/systemd, install/uninstall lifecycle.
- `cli.py`: argument handling and error reporting.
- `__main__.py`: minimal delegation to the CLI.
- Do not introduce unnecessary classes or framework abstractions.

Important simplifications:

- Make the main install flow easy to read: determine plan → stage registrations → render → load/verify images → apply registrations → write Quadlet/YAML → restart affected services → write version markers.
- The main install function should read as that lifecycle sequence. Helper names should make persistent writes and service restarts obvious.
- Avoid surprising side effects in `render()` where practical; make persistent generated-secret creation explicit.
- Split `registration_stage()` if that improves readability.
- Reduce duplicated component truth between `bundles.yaml` and hardcoded Python where this can be done simply, but do not build a generic plugin system.
- Keep standalone manifest support used by examples/tests, but isolate it from the main component lifecycle. Do not remove supported examples as part of this refactor.

Behavior preservation:

- Preserve existing prepare/install/upgrade/uninstall behavior, including component isolation, core version rules, restart decisions, persistent state retention and explicit data deletion.
- Preserve validation order and failure semantics, including which persistent files may have changed when an operation fails.
- Explicit generated-secret creation must not happen earlier than today.
- Treat the lifecycle sequence above as a readability goal, not permission to reorder safety checks.
- Do not silently fix unrelated bugs. Report discovered issues separately.

fapolicyd:

- Support multiple Python files using directory trust.
- Trust only `<release>/deployment/` recursively with the existing per-bundle trust file.
- On upgrade, remove the old release’s `deployment/` trust entry after the new release has been verified successfully.
- Do not trust the whole release and do not add new allow/crun/memfd rules.
- Keep SELinux/fapolicyd hardening unchanged.
- Update trust verification and cleanup to match the directory-based approach.

Bundling:

- Keep `bundle.py` mostly as-is.
- Include `deployment/` in offline bundles.
- Never include `.pyc`, `__pycache__`, generated secrets or private state.
- Keep all checksum guarantees.
- Ensure imports and resource paths work both from the source checkout and from an unpacked offline bundle.

Tests/docs:

- Adapt existing tests; preserve Python 3.6 compatibility.
- Run product tests, acceptance-framework tests, ruff, format check, pyright, vermin and shellcheck.
- Add focused regressions for the root entrypoint, package contents in bundles, no bytecode files, unchanged prepare/install/uninstall behavior, and directory-based fapolicyd trust/upgrade cleanup.
- Check that failed validation or image verification preserves existing deployed state as before.
- Update README/trust instructions and stale monolithic service names.
- Add a short `ARCHITECTURE.md` explaining module responsibilities, the lifecycle flow, shared core versus independent components, and persistent state versus disposable release files.
- Report acceptance-framework tests separately from actual target-host acceptance runs. If no lab is available, state explicitly that directory trust remains unverified on the target.
- If a required check cannot run, report the reason rather than treating it as passed.

Prefer a mechanical move with passing tests first, followed by focused readability improvements. Prefer simpler code over more generic code.

Do the refactor, run the checks, and report:

1. New structure.
2. What moved where.
3. Any intentional or discovered behavior differences, including the required fapolicyd trust change.
4. Test and static-check results, clearly distinguishing local checks from target-host verification.
5. Anything intentionally left for later, including unrelated issues discovered during the work.

## 2. PostgreSQL password rotation

Status: planned; separate from the deploy refactor.

- Define an explicit operator-controlled procedure coordinating the database role
  password, persistent secret file and running clients for core/app1/app2.
- Use the existing ownership, file paths, Secret keys and volume mapping in
  [README.md](README.md#postgresql-configuration-and-credentials).
- Define failure handling and verification before selecting a mechanism. Verify
  authentication after rotation and retention of database data.
- Keep session keys, demo-user passwords, OIDC keys and certificates outside this
  database-specific procedure. Never rotate implicitly during install or upgrade.

## 3. Database backup and credential recovery procedures

Status: planned; separate from password rotation.

- Document and exercise coordinated backup/restore of database volumes and their
  persistent password files, including private permissions.
- Define an explicit recovery procedure for missing credentials or a mismatched
  database password, with operator prerequisites and authentication checks.
- Preserve refusal to generate a replacement password when database state exists.
  Do not delete/reinitialize volumes or assume that changing the secret file
  changes the PostgreSQL role password.
- Keep credentials and connection strings out of logs and acceptance evidence.

## 4. Migration from retained monolithic 0.1.x installations

Status: requires investigation and an explicit migration plan.

- Inventory old services, config, credentials and database volumes before defining
  a migration to core/app1/app2/help.
- Define backup, identity/data mapping, service transition and recovery steps.
- Verify retained application data and credentials on a real migration fixture.
- Do not add automatic migration or destructive cleanup to normal upgrades.

## 5. Close documented runtime verification gaps

Status: planned verification work; current evidence remains unchanged.
The retained 0.2.0 upgrade scenario below is implemented as part of item 10;
run the [focused lab scenario](acceptance/TEST-BASELINE.md#run-the-historical-upgrade-in-the-lab)
and cross-reference its evidence here rather than implementing it again.

- Run a full retained 0.2.0 → 0.2.1 upgrade with the documented manual DB config
  additions, verifying existing credentials, volumes and sibling state.
  Prioritize this before upgrading an important retained installation. Start with
  the old release's real config, initialized database volumes and credentials;
  apply only the documented manual additions, then install the new images and
  verify authentication, CRUD, persistent data and unaffected siblings. Existing
  legacy-password fixtures do not replace this end-to-end upgrade scenario.
- Verify supported Podman versions beyond the currently tested 5.8.2 before
  claiming runtime coverage for them.
- Verify localized PostgreSQL authentication diagnostics, preserving the distinction
  between authentication refusal and DNS/network failures.
- Run host tooling on an actual Python 3.6 interpreter if a suitable environment
  is available; current Python 3.6 compatibility evidence is static.
- Report local/harness checks separately from actual target-machine results.

Source and existing evidence: [DATABASE-VERIFICATION.md](acceptance/DATABASE-VERIFICATION.md#limits-and-deferred-work).

## 6. Runtime connection strings for existing .NET images

Status: delivery scope decision required; Identity demonstrates the interface,
but does not provide integration for unmodified application images.

- Decide whether existing production images must run without application source
  changes. The current `DatabaseEnvironment.cs` runs inside Identity and requires
  application integration; it is not a reusable external launcher.
- If required, provide a small in-image launcher or equivalent derived-image
  integration that builds `ConnectionStrings__Default` at runtime using a proper
  connection-string builder, then starts the unchanged application.
- Preserve the existing config/Secret model, special-character handling, password
  file semantics, offline packaging and signal/exit-code behavior. Do not render
  credentials into YAML, write connection strings to disk or add host-trust rules.
- Verify a real unchanged target application consumes the environment value and
  connects with the correct secret, rejects an incorrect secret, and has no old
  file-based fallback. Report actual tested image and Podman versions.

## 7. PostgreSQL preflight manifest compatibility

Status: follow up when adding another PostgreSQL image or mount layout.

- Document and test the current assumptions in `database_preflight()`, including
  the `/var/lib/postgresql/data` mount and explicit Secret `items` mapping.
- Before supporting a different layout, ensure the guard identifies its actual
  password source and persistent database volume. Unsupported layouts must fail
  clearly before secret generation or persistent changes.
- Add focused regressions for each newly supported layout. Keep database-state
  checks in the lifecycle layer and avoid a generic PostgreSQL framework.

Review source for items 6–7 and the expanded upgrade scenario: static code review
of `improvements-0-2` through `87f4e98`. These are follow-up requirements and
verification gaps, not evidence of completed runtime support.

## 8. Rename core to platform

Status: planned; before item 9 and the deploy refactor. The later separate-bundle clarification above takes precedence over the original bundle assumptions in this task.

Gi den delte komponenten `core` navnet `platform` i `gunstein/podman_offline`.

Dette er en avgrenset navneendring. Behold arkitektur, funksjonalitet, sikkerhetskontroller og komponentisolasjon. Ikke gjennomfør modulrefaktoreringen samtidig.

### 1. Mål og begrepsbruk

Bruk `platform` om den delte komponenten som inneholder Identity, identitetsdatabasen og HTTPS-proxyen.

App1, app2 og help skal fortsatt ha samme avhengighet til denne komponenten som de i dag har til core.

Omdøpingen skal være konsekvent i aktiv kode, konfigurasjon, manifester, tester og dokumentasjon.

### 2. Kartlegg alle berørte navn før endringer

Undersøk blant annet:

- `components/core/`.
- `CORE_VERSION`.
- Bundle-definisjoner og descriptors.
- Funksjoner, variabler og feilmeldinger.
- Persistent komponentmappe og installed-markør.
- Quadlet-/systemd-navn.
- Pod-, Secret-, PVC- og ConfigMap-navn.
- Hostnames og `DB_HOST`.
- Registrerings- og importarkivnavn.
- Sertifikatgenerering og tilhørende filstier.
- Dev-script, acceptance-script og fixtures.
- README, verifikasjonsrapporter og backlog.

Skill mellom navn som tilhører komponenten, eksterne begreper og historiske referanser. Ikke bruk ukritisk global søk-og-erstatt.

### 3. Ønsket navngivning

Bruk blant annet:

```text
components/platform/
PLATFORM_VERSION

/var/lib/myproduct/platform/config.yaml
/var/lib/myproduct/installed/platform

myproduct-platform.service
myproduct-platform.kube
myproduct-platform.yaml
```

Ressurser med komponentprefikset `core-` skal få `platform-`, eksempelvis:

```text
platform-identity
platform-identity-postgres
platform-identity-data
platform-database-password
platform-routes
platform-clients
```

Oppdater alle referanser til de omdøpte ressursene.

Behold navn som ikke trenger å endres:

- Produktnavnet `myproduct`.
- Det delte nettverket `myproduct`.
- App1/app2/help og deres egne ressurser.
- Offentlige URL-paths som `/identity/`, `/app1/`, `/app2/` og `/help/`.
- Databasebrukere og databasenavn, eksempelvis `identity`.
- OIDC-klient-ID-er og scopes.
- Image-repositorier som ikke inneholder komponentnavnet.

Ikke endre credentials eller sertifikatinnhold bare fordi komponenten får nytt navn.

### 4. Bundle-modell og kommandoer

Bundle-modellen skal bli:

```yaml
app1: [platform, app1]
app2: [platform, app2]
help: [help]
```

Behold de tre eksisterende bundle-typene og deres filnavnmønstre:

```text
myproduct-app1-<version>-offline.tar.gz
myproduct-app2-<version>-offline.tar.gz
myproduct-help-<version>-offline.tar.gz
```

Det skal ikke opprettes en separat platform-bundle.

Behold rotkommandoene. Oppdater komponentargumentene:

```sh
./deploy init-config platform
./deploy uninstall platform
./deploy uninstall platform --delete-data
```

Gamle `core`-argumenter skal ikke utføre utilsiktede operasjoner. Gi en tydelig melding om nytt navn dersom de brukes.

Platform skal fortsatt:

- Installeres sammen med første app.
- Beholdes ved lik platform-versjon, med eksisterende regler for registreringsendringer og restart.
- Oppgraderes ved nyere platform-versjon.
- Avvise nedgradering.
- Ikke kunne avinstalleres mens app1, app2 eller help krever den.

### 5. Eksisterende installasjoner og migrering

Omdøpingen berører persistente ressursnavn. Den må ikke føre til at en eksisterende database erstattes av et nytt tomt volum uten at operatøren forstår det.

Denne oppgaven gir ikke tillatelse til å slette, resette eller migrere eksisterende produksjonsstate automatisk.

Bruk følgende avgrensning:

- Implementer den nye navngivningen for nye installasjoner.
- Ikke implementer automatisk migrering fra `core` til `platform`.
- Oppdag gammel core-layout og avvis operasjoner som ellers kan opprette en parallell platform-installasjon eller påvirke gammel state.
- Feil før generering av nye secrets, image-operasjoner, skriving av installert config/registreringer eller endringer i tjenester.
- Gi en tydelig melding om at gammel installasjon krever en separat migreringsprosedyre eller en eksplisitt ny installasjon.
- Avvis også blandet core/platform-state fremfor å gjette hvilken som er autoritativ.

Kontrollen må ikke bare bruke installed-markøren. Undersøk relevante gamle config-/tjenestefiler og persistente databasevolumer, siden avinstallasjon kan ha beholdt data.

Hold kontrollen konkret og avgrenset til produktets kjente ressurser. Feil ved nødvendige tilstandskontroller skal ikke tolkes som fravær.

Behold gamle filer og volumer urørt ved avvisning. Ikke legg til en automatisk «cleanup»-funksjon.

Dokumenter kompatibilitetsbruddet tydelig. Eksisterende installasjoner skal fortsatt kunne administreres med sin tidligere release.

### 6. Versjonering

Ikke publiser endringen under samme releaseversjon som eksisterende layout.

Oppdater `VERSION` og den nye `PLATFORM_VERSION` i tråd med prosjektets versjoneringspraksis, og forklar at navneendringen påvirker oppgraderingskompatibilitet.

Ikke endre image-tags dersom image-innholdet er uendret. Hvis image-innhold faktisk må endres, bruk nye tags og behold prinsippet om immutable release-tags.

### 7. Tester

Oppdater eksisterende tester til den nye navngivningen uten å svekke assertions.

Verifiser minst:

- Korrekte platform-prefikser og referanser i rendret YAML.
- Initialisering av platform-config.
- App-config arver de riktige felles verdiene fra platform.
- App1 og app2 kan hver være første installerte app.
- Help alene avvises.
- Lik, nyere og eldre `PLATFORM_VERSION` håndteres som før.
- Help-only og app-only upgrade beholder upåvirkede komponenter.
- Databasepassord og databasevolumer er koblet korrekt.
- Platform-uninstall blokkeres når dependenter finnes.
- `--delete-data` bare retter seg mot valgt komponents ressurser.
- Bundle-innhold, image-utvalg og checksums er korrekte.
- Gammel core-layout og blandet layout avvises uten endringer.
- Gamle core-databasevolumer oppdages selv om installed-markøren mangler.
- Feil ved tilstandskontroll gir kontrollert avvisning.

Behold historiske fixtures og historiske release-kilder når de faktisk skal representere gammel kode.

En test som tidligere oppgraderte fra en core-basert release kan ikke bare gis nye navn og fortsatt hevde å teste den historiske oppgraderingen. Behold relevant historisk dekning, men test tydelig avvisning ved denne nye kompatibilitetsgrensen.

### 8. Dokumentasjon og opprydding

Oppdater aktive beskrivelser, kommandoer, filstier og diagrammer til `platform`.

Søk gjennom hele repoet etter relevante forekomster av `core`, `CORE_VERSION` og `core-`.

Forklar bevisst beholdte forekomster, eksempelvis:

- Gammel-layout-deteksjon.
- Historiske fixtures.
- Tidligere verifikasjonsrapporter.
- Dokumenterte migreringsbegrensninger.

Ikke omskriv gamle testresultater eller historisk evidence slik at det ser ut som de ble kjørt med platform-layout.

Oppdater backlog med eventuell fremtidig migreringsoppgave. Ikke bland den inn i modulrefaktoreringen.

### 9. Verifikasjon og rapport

Kjør:

- Alle produkttester.
- Alle acceptance-harness-tester.
- Relevante ruff-, format-, pyright-, vermin- og shellcheck-kontroller.

Behold Python 3.6-kompatibilitet for host-verktøyene.

Kjør relevante nye installasjons- og livssyklusscenarioer i det etablerte labmiljøet dersom dette er tilgjengelig og autorisert. Ikke slett eksisterende state eller reset andre miljøer.

Skill mellom lokale tester, harness-tester og faktiske målmaskinkjøringer.

Rapporter:

1. Hvilke navn og filer som er endret.
2. Hvilke navn som bevisst er beholdt.
3. Hvordan gammel og blandet layout oppdages og avvises.
4. Konsekvensen for eksisterende installasjoner.
5. Versjonsendringer.
6. Testresultater og verifikasjonshull.
7. Arbeid som er utsatt, særlig eventuell migrering.

Foretrekk enkel og konsekvent navngivning fremfor et generisk alias- eller kompatibilitetsrammeverk.

## 9. Extract Identity into a separate component and bundle

Status: planned; after the naming change in item 8 and before the deploy refactor. Platform and Identity are separate bundles with explicit dependencies.

Skill Identity ut av `platform` som en egen komponent med en egen separat offline-bundle i `gunstein/podman_offline`.

Dette er en funksjonell oppdeling som skal gjøres før den planlagte modulrefaktoreringen. Ikke gjennomfør modulrefaktoreringen samtidig.

### 1. Undersøk dagens løsning først

Les gjeldende kode, bundle-definisjoner, avhengighetsmodell, tester og dokumentasjon.

Platform er allerede ment som en separat bundle. Ikke ta utgangspunkt i den tidligere modellen hvor app-bundler inkluderte core/platform.

Gjenbruk eksisterende mekanismer for komponenter, bundles, versjoner og avhengigheter. Ikke innfør et parallelt system eller et generisk plugin-rammeverk.

Registrer baseline-commit og kjør eksisterende produkt- og acceptance-harness-tester før endringer.

### 2. Ønsket ansvarsdeling

Etter oppdelingen skal:

| Komponent | Ansvar |
|---|---|
| `platform` | HTTPS-proxy, proxyens TLS-materiale og offentlige ruteregistreringer |
| `identity` | IdentityServer, identitetsdatabase, databasepassord, signeringsmateriale, Data Protection-state, demobrukere og OIDC-klientregistreringer |
| `app1` | App1, egen database og egne credentials |
| `app2` | App2, egen database og egne credentials |
| `help` | Hjelpeinnhold og egen ruteregistrering |

Behold eksisterende eierskap og sikre livssyklusregler for delt nettverk og eventuell felles demo-CA. Ikke slett eller regenerer felles materiale som følge av oppdelingen.

Kartlegg alle eksisterende ressurser og filer før flytting, slik at ingen persistent state blir glemt.

### 3. Separate bundles og eksplisitte avhengigheter

Bruk følgende logiske modell:

| Bundle | Innhold | Avhengigheter |
|---|---|---|
| `platform` | Platform-komponenten | Ingen |
| `identity` | Identity-komponenten | Platform |
| `app1` | App1-komponenten | Platform og identity |
| `app2` | App2-komponenten | Platform og identity |
| `help` | Help-komponenten | Platform |

Hver bundle skal bare inneholde egne komponentressurser og nødvendige images, i tillegg til felles deploy-kode og nødvendige metadata/defaults.

App-bundler skal ikke inkludere eller installere platform/identity automatisk. Identity-bundlen skal ikke inkludere platform.

Manglende avhengighet skal gi en tydelig feil. Ikke forsøk nettverksnedlasting eller automatisk installasjon fra andre release-mapper.

Oppdater eksisterende bundle-bygging slik at alle definerte bundles produseres, inkludert separat identity-bundle, med prosjektets etablerte filnavnmønster.

### 4. Versjoner og kompatibilitet

Identity skal kunne versjoneres og oppgraderes uavhengig av platform og appene.

Bruk eksisterende versjoneringsmodell. Hvis denne bruker separate versjonsfiler, innfør en tilsvarende `IDENTITY_VERSION`. Ikke opprett et nytt versjoneringssystem hvis repoet allerede har en egnet modell.

Avhengigheter skal ha eksplisitte, dokumenterte versjonskrav. Gjenbruk eksisterende syntaks og sammenligningsregler. Hvis slike krav ikke finnes, innfør den minste mekanismen som dekker behovet, og begrunn valget.

Valider:

- At avhengighetene er installert.
- At deres versjoner tilfredsstiller innkommende bundles krav.
- At oppgradering av platform eller identity fortsatt tilfredsstiller kravene til installerte dependenter.

Oppbevar nødvendig avhengighetsmetadata som installert state. Kontrollene skal ikke avhenge av at gamle release-mapper fortsatt finnes.

Ikke anta kompatibilitet bare fordi en versjon er nyere.

Behold eksisterende regler for reinstallasjon og nedgradering der de fortsatt er relevante. Dokumenter eventuelle nødvendige endringer.

Alle avhengighets- og versjonsavvisninger skal skje før secret-generering, image-load, skriving av registreringer/tjenestefiler eller restart.

### 5. Skill ruteregistreringer fra OIDC-klientregistreringer

I dagens samlede løsning kan begge registreringstypene påvirke samme komponent. Etter oppdelingen skal eierskapet være tydelig:

- Platform konsumerer offentlige ruter.
- Identity konsumerer offentlige OIDC-klientregistreringer.
- Appene eier sine private klientnøkler og leverer bare offentlig klientmetadata og sertifikat til identity.
- Identity registrerer sin egen offentlige route hos platform.
- Help registrerer bare en route hos platform.

Behold indeksmekanismen som hindrer at gamle filer i importvolumer holder fjernede ruter eller klienter aktive.

Restartbeslutninger skal være separate:

| Endring | Forventet påvirkning |
|---|---|
| Bare app-route endres | Platform oppdateres/restartes |
| Bare OIDC-klientregistrering endres | Identity oppdateres/restartes |
| Begge endres | Begge berørte komponenter oppdateres/restartes |
| Ingen registrering endres | Ingen unødvendig restart av platform/identity |
| Help-route endres | Platform påvirkes, identity beholdes |
| Identity oppgraderes uten endret offentlig route | Identity påvirkes, platform beholdes |

Appenes containere skal ikke restartes bare fordi platform eller identity restartes. Et kort avbrudd i tilgjengelighet eller innlogging er noe annet enn restart av appene.

Ikke legg til nye registreringskommandoer hvis eksisterende installasjonsflyt kan håndtere dette tydelig.

### 6. Behold den offentlige innloggingskontrakten

Oppdelingen skal ikke samtidig endre:

- `/identity/`.
- Offentlig issuer-URL.
- Appenes klient-ID-er og scopes.
- Redirect-URI-er.
- `/app1/`, `/app2/` og `/help/`.
- Appenes cookie-navn og paths.

Oppdater interne hostnames og upstream-referanser der det er nødvendig.

Platform skal kunne kjøre og betjene help uten at identity er installert. Proxykonfigurasjonen må ikke kreve at en fraværende identity-tjeneste kan DNS-resolves ved oppstart.

Verifiser fortsatt delt innlogging mellom app1 og app2.

### 7. Config, secrets og database

Identity skal få egen komponentconfig og persistent mappe:

```text
components/identity/config.defaults.yaml
/var/lib/myproduct/identity/config.yaml
```

Følg eksisterende configmodell:

- Defaults brukes ved initialisering og dev.
- Produksjon bruker autoritativ persistent komponentconfig.
- Upgrade overskriver ikke eksisterende config.

Identity skal arve relevante felles verdier fra installert platform ved config-initialisering, etter samme etablerte prinsipp som øvrige dependenter.

Flytt identity-spesifikke DB-innstillinger, Secret-/volumdefinisjoner og generated-secret-oppføringer ut av platform.

Behold:

- Én persistent kilde for hvert databasepassord.
- Samsvar mellom PostgreSQL-server og klient.
- Beskyttelse mot å generere nytt passord når database-state allerede finnes.
- Runtime-bygging av `ConnectionStrings__Default`.
- Korrekt escaping og sikker feilhåndtering.
- Eksisterende databasebruker og databasenavn hvis det ikke finnes en nødvendig grunn til å endre dem.

Ikke innfør passordrotasjon, databaseprivilegium-endringer eller schema-migrering i denne oppgaven.

### 8. Eksisterende installasjoner: ikke migrer automatisk

Oppdelingen berører persistent identitetsdatabase, credentials, signeringsnøkler, Data Protection-state og klientregistreringer.

Denne oppgaven gir ikke tillatelse til automatisk flytting, sletting eller reinitialisering av eksisterende installert state.

Implementer ny layout for nye installasjoner. Oppdag eksisterende layout hvor identity fortsatt inngår i platform, og avvis inkompatibel installasjon/oppgradering før endringer.

Kontrollen skal også håndtere:

- Beholdte databasevolumer uten installed-markør.
- Blandet gammel og ny layout.
- Delvis eksisterende credentials eller tjenestefiler.
- Feil ved nødvendige tilstandskontroller.

Ikke bruk eksistensen av platform alene som tegn på gammel layout; platform er også en gyldig selvstendig komponent i den nye modellen.

Gi en tydelig melding om at den gamle layouten krever en separat migreringsprosedyre eller eksplisitt ny installasjon. La eksisterende state være urørt og fortsatt administrerbar med tidligere release.

Ikke lag tom identitetsdatabase eller nye signeringsnøkler som skjult erstatning for gammel state.

Dokumenter kompatibilitetsbruddet og før eventuell migrering som egen backlog-oppgave.

### 9. Avinstallasjon

Avhengigheter skal styre avinstallasjon:

- Identity kan ikke fjernes mens installerte apper krever den.
- Help skal ikke blokkere avinstallasjon av identity.
- Platform kan ikke fjernes mens identity, app1, app2 eller help krever den.

Når en app fjernes:

- Fjern dens route fra platform.
- Fjern dens offentlige OIDC-klientregistrering fra identity.
- Oppdater/restart bare de berørte tjenestene.
- Behold andre komponenters registreringer, tjenester og data.

Når identity fjernes uten dependenter:

- Fjern dens route fra platform.
- Behold platform og eventuell help.
- Behold identity-data som standard.

`--delete-data` skal bare slette valgt komponents egne data. Delt nettverk, felles CA og andre komponenters credentials skal ikke slettes.

### 10. Dev og bundling

Dev skal bruke samme komponentdeling og registreringsmodell som produksjon, selv om dev-helperen starter hele demosystemet samlet.

Oppdater image-bygging, image-utvalg og bundling etter behov.

Behold:

- Manifestdrevet image-utvalg.
- `imagePullPolicy: Never`.
- Ekskludering av privat state og bytecode.
- Checksums for alle leverte filer.
- Eksisterende fapolicyd- og SELinux-modell.

Identity-bundlen skal kunne transporteres og oppgraderes alene uten at platform- eller app-bundler må overføres på nytt.

Ikke endre immutable image-tags uten å bygge tilsvarende nye images.

### 11. Tester

Oppdater eksisterende tester uten å svekke sikkerhets- eller isolasjonskontroller. Legg til fokuserte tester for:

#### Installasjon og avhengigheter

- Platform kan installeres alene.
- Platform og help fungerer uten identity.
- Identity uten platform avvises før endringer.
- App uten identity avvises før endringer.
- Begge apprekkefølger fungerer etter platform og identity.
- Manglende og inkompatible avhengigheter gir tydelige feil.
- Oppgradering som bryter installerte dependenters versjonskrav avvises.

#### Registreringer og restart

- Bare route-endring påvirker platform.
- Bare klientendring påvirker identity.
- Begge endringer påvirker begge.
- Uendrede registreringer gir ingen unødvendig restart.
- Fjernede ruter/klienter er ikke aktive gjennom gamle importfiler.

#### Selvstendig identity-upgrade

Legg til et reelt acceptance-scenario som:

1. Installerer platform, identity og begge apper.
2. Oppretter brukerdata og verifiserer innlogging.
3. Bygger og overfører bare en nyere identity-bundle.
4. Installerer denne.
5. Verifiserer at ny identity-versjon og nytt image faktisk kjører.
6. Verifiserer innlogging og appenes databaseoperasjoner.
7. Verifiserer at identity-data og eksisterende credentials er beholdt.
8. Verifiserer at platform og appenes versjoner, tjenesteprosesser og konfigurasjon er uendret når registreringene ikke er endret.

Bruk en observerbar endring eller image-identitet som bevis; en oppdatert versjonsmarkør alene er ikke tilstrekkelig.

#### Avinstallasjon og gammel state

- Identity-avinstallasjon blokkeres av apper, men ikke help.
- Platform-avinstallasjon blokkeres av dependenter.
- Data beholdes som standard.
- Eksplisitt sletting er avgrenset til riktig komponent.
- Gammel samlet platform/identity-layout og blandet layout avvises uten endringer.

Behold relevant eksisterende dekning for help-only upgrade, app-only upgrade, offline installasjon, reboot og persistens. Tilpass forventningene til separate bundles.

### 12. Dokumentasjon

Oppdater README og relevant arkitektur-/testdokumentasjon slik at det er enkelt å forstå:

- Hva hver komponent eier.
- Hva hver bundle inneholder.
- Installasjonsrekkefølgen.
- Hvordan avhengigheter og versjonskrav kontrolleres.
- Hvem som konsumerer ruter og OIDC-klienter.
- Hvilke endringer som restarter hvilke tjenester.
- Hvordan identity oppgraderes alene.
- Hvilken state som er persistent.
- Hvorfor gammel samlet layout ikke oppgraderes automatisk.

Oppdater aktive kommandoeksempler og fjern foreldede antakelser om at app-bundler inneholder platform.

Ikke omskriv historiske verifikasjonsrapporter som om de ble kjørt med den nye arkitekturen.

### 13. Verifikasjon og leveranse

Kjør:

- Alle produkttester.
- Alle acceptance-harness-tester.
- Relevante ruff-, format-, pyright-, vermin- og shellcheck-kontroller.

Behold Python 3.6-kompatibilitet for host-verktøyene.

Kjør relevante faktiske acceptance-scenarioer i etablert labmiljø dersom dette er tilgjengelig og autorisert. Ikke reset eller endre andre miljøer.

Skill tydelig mellom lokale tester, harness-tester og målmaskinkjøringer. Hvis labkjøring ikke kan utføres, rapporter hvilke garantier som fortsatt er uverifisert.

Rapporter:

1. Ny komponent- og bundle-struktur.
2. Ressurser og state som har fått ny eier.
3. Avhengighets- og versjonsmodellen.
4. Restartreglene for ruter og klienter.
5. Konsekvensen for eksisterende installasjoner.
6. Testresultater og verifikasjonshull.
7. Utsatt arbeid, særlig migrering og modulrefaktorering.

Hold funksjonell oppdeling og senere modulrefaktorering adskilt. Foretrekk eksplisitte, enkle regler fremfor generelle abstraksjoner.
