# Backlog

Planned work, not implemented behavior. Each item requires separate implementation
and verification. Item numbers are stable references, not execution priority.
The recommended implementation sequence through item 1 is complete. Remaining
items retain their individual scopes below; agree the next priority separately.

Implemented: test baseline (item 10, commit `511099e`) and rename/separate
platform bundle (item 8), separate Identity bundle (item 9, 0.4.0), and credential
path cleanup (item 12, 0.4.1; [verification](acceptance/CREDENTIAL-PATHS.md)), and
retry-safe lifecycle operations (item 13, 0.4.2; [verification](acceptance/RETRY-SAFETY.md)),
and deploy package refactor (item 1, 0.4.3; [verification](acceptance/DEPLOY-REFACTOR.md)),
and app credential delivery cleanup (item 14, 0.4.4; [verification](acceptance/CREDENTIAL-DELIVERY.md)),
and removal of obsolete layout checks (item 15, 0.4.5; [verification](acceptance/LEGACY-CHECK-CLEANUP.md)).
See [Identity verification](acceptance/IDENTITY-SPLIT.md). Lab verification remains pending; it does not
block the next implementation step. Run the historical upgrade at `511099e` and
current platform/lifecycle scenarios separately; see [platform verification](acceptance/PLATFORM-RENAME.md).

Item 15 removes historical layout refusal checks; the earlier task descriptions
and reports retain their original scope and are not current requirements.

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

Status: implemented locally at `511099e`; historical lab verification pending. Item 8 proceeded with explicit user authorization.
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

Status: implemented in 0.4.3 after items 10, 8, 9, 12 and 13. Local checks passed;
real directory trust remains unverified on the target. See [verification](acceptance/DEPLOY-REFACTOR.md).
No existing installation requires migration: this implementation adds no migration,
old-module fallback or compatibility layer. The original task follows.

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

Status: superseded by the clarification in item 15: no existing installations
require migration. The original proposal below is retained as history, not
planned implementation work.

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

Status: implemented locally in 0.3.0; fresh platform/refusal lab verification pending.
The user explicitly selected a separate platform bundle for this step. Platform
still contains Identity until item 9. The original task below is retained;
[PLATFORM-RENAME.md](acceptance/PLATFORM-RENAME.md) describes the delivered model,
compatibility boundary and checks. The later separate-bundle clarification takes
precedence over the original embedded-platform assumptions in this task.

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

Status: implemented in 0.4.0; real lab verification pending. Platform and Identity are separate bundles with explicit dependencies. See [Identity verification](acceptance/IDENTITY-SPLIT.md). The original task follows.

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


## 11. Plan an explicit retained core-to-platform migration

Status: superseded by the clarification in item 15: no existing installations
require migration. The original proposal below is retained as history, not
planned implementation work.

0.3.0 deliberately refuses retained or mixed core/platform state. Design and
review a separate procedure before migrating an important 0.2.x installation.
Inventory config, all credentials/certificates and CA, database and Data
Protection volumes, public registrations/imports, versions/dependencies,
Quadlet/systemd files and trust. Specify backups/restoration, volume identity/data
retention, explicit operator steps, verification and failure recovery. Preserve
password bytes and existing keys; never create an unnoticed empty replacement
database. Test against real historical releases and representative retained data.
Do not implement automatic rename, cleanup, resets or migration as part of item 1.
Include both retained core 0.2.x and combined platform/Identity 0.3.x sources.
Target the separate platform/Identity layout of 0.4.0; neither old layout is
automatically migrated. Coordinate backups, ownership and explicit transitions
with item 9 before implementing a procedure.

## 12. Rename component credential paths

Status: implemented in 0.4.1; fresh-install lab verification pending. See
[credential-path verification](acceptance/CREDENTIAL-PATHS.md). The deploy
refactor (item 1) is implemented; see its verification report.
This task uses fresh state only and requires no migration or backward compatibility.
The full agent message follows, with heading levels adjusted for this document.

Erstatt katalognavnet `generated-certificates/` med `credentials/` for komponentenes passord, sesjonsnøkler, private nøkler og sertifikater i `gunstein/podman_offline`.

Navnet `generated-certificates` beskriver innholdet feil: mappen inneholder også databasepassord og sesjonsnøkler, og materialet kan være både generert og eksternt levert.

Dette er en avgrenset opprydding av filstier. Ikke kombiner den med modulrefaktorering, passordrotasjon eller andre arkitekturendringer.

### 1. Ingen migrering eller bakoverkompatibilitet

Det finnes ingen eksisterende installasjoner som skal oppgraderes.

Implementer bare den nye layouten:

- Ikke lag migreringskode.
- Ikke lag fallback til `generated-certificates/`.
- Ikke legg til aliaser eller kompatibilitetsgrener.
- Ikke lag en flytteprosedyre for gammel state.
- Bruk fersk, isolert state i testene.

Sletting av andre eksisterende filer, credentials eller databasevolumer inngår ikke i oppgaven.

Historiske verifikasjonsrapporter og evidence skal beholdes uendret.

### 2. Undersøk gjeldende kode

Ta utgangspunkt i faktisk repo-status, inkludert eventuell gjennomført omdøping fra core til platform og utskilling av identity.

Kartlegg aktive referanser til `generated-certificates`, blant annet i:

- Komponentenes config-defaults.
- `GENERATED_SECRETS`, `SECRET_FILES` og `VOLUME_FILES`.
- Sertifikatscript og andre generatorer.
- OIDC-klientdescriptors og offentlig sertifikatregistrering.
- Database-preflight.
- Dev-script og smoke-tester.
- Acceptance-script og persistensobservasjoner.
- Bundle-beskyttelse mot private filer.
- README, PKI-dokumentasjon og eksempler.

### 3. Ny standardstruktur

Bruk `credentials/` under hver komponents state-mappe.

For app1 kan strukturen være:
```
/var/lib/myproduct/app1/
├── config.yaml
└── credentials/
    ├── database/
    │   └── password
    └── todo/
        ├── session-key
        ├── todo-client.key
        ├── todo-client.crt
        └── ca.crt
```

Dev bruker tilsvarende:
```
build/dev/app1/credentials/
```

Oppdater config, eksempelvis:
```
GENERATED_SECRETS:
- credentials/todo/session-key
- credentials/database/password

SECRET_FILES:
  app1-database-password:
  - credentials/database

VOLUME_FILES:
  app1-signing:
  - credentials/todo
```

Bruk samme prinsipp for øvrige komponenter.

Behold eksisterende undermapper og filnavn når de fortsatt er meningsfulle. Ikke utvid oppgaven til en generell reorganisering av credentials.

Felles PKI/CA-state utenfor komponentenes `generated-certificates/` skal ikke flyttes som en bieffekt.

### 4. Behold eksisterende funksjonalitet

Dette er en endring av host-side filstier. Behold:

- Secret-navn og keys.
- PVC-/volumnavn.
- Pod- og tjenestenavn.
- Containerens mount-paths, eksempelvis `/run/secrets/database/password` og `/certificates`.
- Databasebrukere og databasenavn.
- OIDC-klient-ID-er, scopes og offentlige URL-er.
- Runtime-mekanismen for connection strings.
- Config-precedence og autoritativ persistent produksjonsconfig.

Oppdater alle host-side referanser, også sertifikatstier i `client.yaml` eller tilsvarende descriptors.

Unngå endringer i applikasjonskode og images når containergrensesnittet er uendret.

### 5. Behold genererings- og sikkerhetsreglene

Databasepassord og sesjonsnøkler skal fortsatt genereres gjennom eksisterende `GENERATED_SECRETS`.

Sertifikatscriptet skal skrive sitt materiale til de nye stiene. Ikke flytt databasepassordgenerering tilbake til sertifikatscriptet.

Behold eksisterende garantier:

- Manglende hemmeligheter opprettes bare når dette er tillatt.
- Eksisterende gyldige filer beholdes byte-for-byte ved restart/redeploy.
- Tomme eller ugyldige filer gir feil.
- Manglende databasepassord med eksisterende databasevolum avvises.
- Private fil- og katalogrettigheter beholdes.
- Symlink-escape og utrygge output-stier avvises.
- Credentials og komplette connection strings eksponeres ikke i logger.

Disse kontrollene gjelder vanlig drift av den nye layouten. Det skal ikke innføres egne kontroller eller fallback-regler for gammel layout.

### 6. Dev, bundling og acceptance

Oppdater alle helper-script som leser, genererer, overfører eller sammenligner credentials.

Nye dev- og produksjonsinstallasjoner skal bruke samme layout under sine respektive komponentmapper.

Bundle-beskyttelsen skal fortsatt hindre at credentials følger med offline-arkivene, inkludert kopiering gjennom symlink-aliaser.

Behold kontrollene som følger deklarerte secret-filer. Ikke erstatt dem med bare et enkelt navnefilter for mappen `credentials`.

Behold checksum-garantier, offline-egenskaper og eksisterende SELinux-/fapolicyd-kontroller.

### 7. Tester

Oppdater eksisterende tester og legg bare til fokuserte regresjoner der dekning mangler.

Verifiser:

- Defaults og config-initialisering bruker `credentials/`.
- Genererte filer havner på riktige stier i dev og produksjon.
- Sertifikatscriptet bruker de nye stiene.
- OIDC-klientregistrering finner riktig offentlig sertifikat.
- Server og klient fortsatt bruker samme databasepassord.
- Restart/redeploy beholder credentials byte-for-byte.
- Database-preflight fortsatt avviser manglende passord når volumet finnes.
- Secret-/PVC-navn og container-mounts er uendret.
- Private filer og symlink-aliaser ikke havner i bundles.
- Smoke- og acceptance-script bruker de nye plasseringene.

Ikke legg til migreringstester eller tester som krever støtte for gamle configstier.

### 8. Dokumentasjon og opprydding

Dokumenter rollene tydelig:

- `credentials/` inneholder passord, nøkler og sertifikater.
- `GENERATED_SECRETS` angir hvilke filer som genereres.
- `SECRET_FILES` og `VOLUME_FILES` angir hvordan filene leveres til containerne.

Søk gjennom hele repoet etter `generated-certificates`. Oppdater aktive referanser i kode, config, tester, eksempler og operatørdokumentasjon.

Behold historiske rapporter og eventuelle fixtures som eksplisitt representerer en historisk release. Forklar gjenværende forekomster i sluttrapporten.

Ikke marker tidligere labresultater som verifikasjon av denne endringen.

### 9. Verifikasjon og leveranse

Kjør:

- Alle produkttester.
- Alle acceptance-harness-tester.
- Relevante ruff-, format-, pyright-, vermin- og shellcheck-kontroller med prosjektets eksisterende oppsett.

Behold Python 3.6-kompatibilitet for host-verktøyene.

Kjør relevante ferske installasjons-/e2e-scenarioer i etablert labmiljø dersom dette er tilgjengelig og autorisert. Ikke reset andre miljøer.

Skill tydelig mellom lokale tester, harness-tester og faktisk container-/målmaskinverifikasjon. Oppgi hva som ikke kunne kjøres.

Rapporter kort:

1. Hvilke stier og filer som er endret.
2. Eventuelle bevisst beholdte historiske referanser.
3. Testresultater og verifikasjonshull.
4. Bekreftelse på at det ikke er innført migreringskode eller fallback til gammel layout.

Foretrekk en enkel, konsekvent navneendring fremfor nye abstraksjoner.

## 13. Retry-safe install and uninstall

Status: implemented in 0.4.2; local failure-injection verification passed, real
Podman/systemd behavior remains unverified here. See [retry verification](acceptance/RETRY-SAFETY.md).
This is a bounded correctness fix for retrying failed operations, not a transaction
framework or module refactor. The full agent message follows, with Markdown
formatting adjusted for this document.

Implementer trygg gjentakelse etter feil i installasjon og avinstallasjon i gunstein/podman_offline.

Oppgaven gjelder to konkrete feil i deploy.py:

1. Et nytt installasjonsforsøk kan hoppe over nødvendige omstarter av Identity/platform etter et mislykket forsøk.
2. En avinstallasjon kan bli stående halvferdig, samtidig som neste forsøk avvises fordi installasjonsmarkøren allerede er slettet.

Dette er en avgrenset feilretting. Ikke gjennomfør den planlagte modulrefaktoreringen, endre komponentarkitekturen eller innfør et generelt transaksjonsrammeverk.

### 1. Les og forstå eksisterende flyt

Les først:

- install_components()
- install_component_plan()
- write_registrations()
- registration_stage()
- component_imports()
- uninstall()
- relevante tester for installasjonsfeil, komponenter og Identity

Funksjonsnavnene kan ha endret seg. Finn tilsvarende kode i gjeldende branch.

Komponentmodellen er:

- platform eier proxy og ruteregistreringer.
- identity eier IdentityServer og klientregistreringer.
- app1 og app2 avhenger av platform og identity.
- help avhenger av platform.

Ruteregistreringer og klientregistreringer skal fortsatt behandles separat. En route-endring skal normalt påvirke platform, mens en klientendring skal påvirke identity.

### 2. Feilen ved installasjon

Dagens flyt skriver registreringer før alle nødvendige tjenester er restartet.

Et eksempel:

1. App1 har en ny route og klientregistrering.
2. Installer skriver begge registreringene til persistent state.
3. Restart av app1 feiler.
4. Installer avslutter før Identity og platform er restartet.
5. Operatøren kjører samme installasjon på nytt.
6. Registreringsfilene har allerede riktig innhold og regnes som uendret.
7. Identity og platform blir derfor ikke restartet.

Det andre forsøket kan rapportere suksess selv om de kjørende tjenestene ikke har tatt i bruk registreringene.

En tilsvarende feil kan oppstå dersom skriving av importarkiver eller restart av en av registreringseierne feiler.

Krav: Et nytt installasjonsforsøk må fullføre nødvendig arbeid fra forrige forsøk. Det er ikke tilstrekkelig å sammenligne nye registreringer med filene som allerede ligger på disk.

### 3. Løsning for installasjon

Velg en enkel, eksplisitt mekanisme for å huske ufullført arbeid mellom prosesskjøringer.

En liten persistent pending-fil er et mulig valg. Den kan for eksempel angi at registreringene til identity og/eller platform ennå ikke er bekreftet tatt i bruk.

Det konkrete filnavnet og formatet kan tilpasses eksisterende kode. Følg disse reglene:

- Registrer nødvendig arbeid før endringer som ellers kan gjøre at behovet blir glemt.
- Pending-state skal overleve at installer avslutter eller prosessen avbrytes.
- Ved neste forsøk skal pending-state leses og kombineres med eventuelle nye endringer.
- Nødvendige importarkiver må skrives på nytt dersom forrige forsøk ikke fullførte dette.
- Berørte tjenester må restartes og kontrolleres med eksisterende suksesskriterier.
- Fjern bare pending-state for arbeid som faktisk er fullført.
- Hvis en restart eller kontroll feiler, skal ufullført arbeid fortsatt være registrert.
- Et nytt forsøk med identiske registreringsfiler må fortsatt utføre pending arbeid.

Pending-state skal inneholde bare nødvendig metadata, aldri passord, private nøkler eller komplette konfigurasjoner.

Bruk eksisterende mønstre for private filrettigheter og trygg filskriving. Ikke følg symlinker til vilkårlige steder. Ugyldig pending-state skal gi en tydelig feil, ikke ignoreres.

Ikke løs problemet ved å restarte alle tjenester på hver installasjon.

Bevar normal oppførsel:

- Uendrede registreringer uten pending arbeid skal ikke restarte Identity/platform.
- Bare route-endring skal normalt restarte platform.
- Bare klientendring skal normalt restarte identity.
- Begge endringer skal restarte begge.
- Sibling-applikasjoner skal ikke restartes som en bivirkning.

Hvis du velger en annen løsning enn pending-state, må den dekke de samme feiltilfellene og forklares tydelig.

### 4. Feilen ved avinstallasjon

Dagens avinstallasjon sletter blant annet installasjonsmarkøren før hele operasjonen er fullført.

Et eksempel:

1. App1 stoppes.
2. Quadlet/YAML og registreringer slettes.
3. Installasjonsmarkøren slettes.
4. Restart av Identity eller platform feiler.
5. Operatøren kjører uninstall på nytt.
6. Installer avviser forsøket fordi app1 ikke lenger regnes som installert.

Med --delete-data kan også volumfjerning feile etter at installasjonsmarkøren er borte.

Krav: Operatøren skal kunne gjenta avinstallasjonen og fullføre den uten manuell rekonstruksjon av markører, YAML eller registreringer.

### 5. Løsning for avinstallasjon

Gjør avinstallasjonen mulig å fortsette etter delvis gjennomføring.

Ikke løs dette bare ved å flytte sletting av installasjonsmarkøren til slutten. Tidligere slettet YAML eller andre filer kan fortsatt være nødvendige for å vite hva som gjenstår.

Før destruktive steg må nødvendig informasjon være validert og bevart slik at neste kjøring vet:

- hvilken komponent som avinstalleres
- om operasjonen inkluderer --delete-data
- hvilke tjenester som skal stoppes eller oppdateres
- hvilke registreringseiere som må oppdateres
- hvilke konkrete volumer som eventuelt skal slettes

Bruk en liten, eksplisitt tilstand for pågående avinstallasjon dersom det er nødvendig. Ikke lag en generell operasjonsmotor.

Følg disse kravene:

- Avhengighetskontroller skal fortsatt kjøres før avinstallasjonen starter.
- En komponent med pågående avinstallasjon må ikke behandles som en frisk, tilgjengelig avhengighet for nye installasjoner.
- Gjentatt sletting av filer som allerede er fjernet av samme operasjon skal være trygg.
- Manglende volum ved retry kan regnes som allerede slettet.
- Feil ved kontroll av et volum skal fortsatt være en feil; det må ikke tolkes som at volumet mangler.
- Volumlisten skal komme fra validert, komponentavgrenset informasjon.
- Ikke utvid sletting til andre komponenters volumer eller state.
- Oppdatering av registreringer og nødvendige omstarter må kunne gjentas.
- Marker operasjonen som fullført først når alle nødvendige steg har lykkes.
- Rydd opp i pending-state etter fullført operasjon.

Bevar forskjellen mellom:

- uninstall: behold data, config og credentials.
- uninstall --delete-data: slett bare den valgte komponentens relevante data og state.

Et retry må ikke utilsiktet endre en avinstallasjon uten datasletting til en avinstallasjon med datasletting. Definer og dokumenter hvordan avvikende flagg håndteres. Den enkleste løsningen er å kreve samme valg som da operasjonen startet og gi en tydelig feil ved avvik.

### 6. Samspill mellom installasjon og avinstallasjon

Definer enkel og tydelig oppførsel dersom en ny kommando møter en ufullført operasjon.

For eksempel:

- install må ikke ignorere en pågående avinstallasjon av samme komponent.
- uninstall må ikke slette eller overse pending registreringsarbeid på en måte som etterlater feil runtime-state.
- En operasjon må ikke fjerne pending arbeid som tilhører en annen operasjon.

Det er akseptabelt å avvise en konflikt med en tydelig melding om hvilken kommando operatøren må kjøre for å fullføre først.

Ikke innfør automatisk rollback eller automatiske reparasjoner av ukjent state.

### 7. Tester for installasjon

Bruk eksisterende testoppsett og feilinjeksjon. Legg minst til følgende scenarioer:

#### A. App-restart feiler etter registreringsskriving

1. Installer en app med endret route og klientregistrering.
2. La app-restart feile etter at registreringene er skrevet.
3. Verifiser at installasjonen feiler.
4. Kjør samme installasjon igjen uten feilen.
5. Verifiser at nødvendige importarkiver oppdateres og både Identity og platform restartes.
6. Verifiser at pending-state fjernes etter suksess.

#### B. En registreringseier feiler

1. La restart eller etterfølgende kontroll av Identity/platform feile.
2. Kjør installasjonen igjen.
3. Verifiser at ufullført arbeid utføres, selv om registreringsfilene er identiske.

#### C. Importarkivskriving feiler

1. La skriving av et nødvendig importarkiv feile etter at registreringer er skrevet.
2. Kjør installasjonen igjen.
3. Verifiser at importarkivet faktisk oppdateres før operasjonen regnes som fullført.

#### D. Normal installasjon er fortsatt avgrenset

Verifiser fortsatt de fire kombinasjonene:

- ingen registreringsendring
- bare route-endring
- bare klientendring
- begge endringer

Uten pending arbeid skal ingen ekstra fellestjenester restartes.

### 8. Tester for avinstallasjon

Legg minst til følgende scenarioer:

#### A. Restart av registreringseier feiler

1. Start avinstallasjon av en installert app.
2. La restart av Identity eller platform feile.
3. Kjør avinstallasjonen igjen.
4. Verifiser at den fullføres selv om noen filer allerede er slettet.
5. Verifiser at registreringene er fjernet fra de oppdaterte importarkivene.
6. Verifiser at pending-state ryddes opp.

#### B. Volumsletting feiler

1. Start uninstall --delete-data med flere komponentvolumer.
2. La sletting av et senere volum feile etter at et tidligere volum er fjernet.
3. Kjør samme kommando igjen.
4. Verifiser at allerede slettede volumer håndteres og resterende arbeid fullføres.
5. Verifiser at andre komponenters state er uendret.

#### C. Avinstallasjon uten datasletting

Et mislykket forsøk og retry skal bevare bytes i config og credentials samt databasevolumer.

#### D. Konflikter og ugyldig state

Test:

- retry med avvikende valg for --delete-data
- installasjon mens samme komponent har pågående avinstallasjon
- ny installasjon som krever en komponent med pågående avinstallasjon
- ugyldig eller symlinket pending-state

Retry-testene må representere en ny prosesskjøring: løsningen skal ikke være avhengig av variabler fra første forsøk. Bruk samme persistente testkatalog, men nullstill midlertidig tilstand mellom forsøkene.

### 9. Avgrensning og kompatibilitet

Bevar:

- eksisterende rotkommandoer
- Python 3.6-kompatibilitet for deploy-koden
- bundle-avhengigheter og versjonsregler
- checksums og offline installasjon
- eksisterende secret-generering og credential-stier
- SELinux- og fapolicyd-kontroller
- komponentisolasjon og persistente data

Ikke:

- flytt deploy til en Python-pakke som del av denne oppgaven
- legg til passordrotasjon
- regenerer credentials ved retry
- innfør ny migreringslogikk
- endre normale tjenesteomstarter utover det feilrettingen krever
- legg pending-state i release-katalogen eller offline-bundlen

### 10. Dokumentasjon, sjekker og rapport

Dokumenter kort hvordan operatøren gjentar en mislykket installasjon eller avinstallasjon, og hvordan eventuelle konflikter rapporteres.

Kjør:

- produkttestene
- acceptance-harness-testene
- ruff
- formatkontroll
- pyright
- vermin
- shellcheck

Legg bare til nye reelle acceptance-scenarioer dersom de gir nødvendig dekning utover målrettede feilinjeksjonstester. Ikke påstå at stubbet testing beviser faktisk Podman/systemd-oppførsel.

Rapporter:

1. Årsaken til de to feilene.
2. Hvordan ufullført arbeid lagres og fullføres ved retry.
3. Hvilke filer som er endret.
4. Hvilke nye feilscenarioer testene dekker.
5. Faktiske testresultater og sjekker som ikke kunne kjøres.
6. Eventuelle begrensninger.

Foretrekk små, tydelige funksjoner og eksplisitte steg. Målet er at en middels erfaren Python-utvikler enkelt skal kunne forstå hvorfor et nytt forsøk er trygt.

## 14. Tighten app credential delivery and remove unused API secret

Status: implemented in 0.4.4; local checks and real target verification are
reported in [credential delivery](acceptance/CREDENTIAL-DELIVERY.md). Target
verification remains pending. The original agent message follows.

Rett credential-håndteringen i `gunstein/podman_offline` med en liten, målrettet endring.
Behold dagens komponentarkitektur og offline installasjonsmodell.

### 1. Bakgrunn og bekreftede observasjoner

App1 og app2 deklarerer `credentials/todo/session-key` i `GENERATED_SECRETS`.
Hele `credentials/todo/`, inkludert session key og privat klientnøkkel, leveres i dag
gjennom `VOLUME_FILES` til appens signing-PVC og monteres skrivebeskyttet på
`/certificates` i backend. Frontend får ikke denne mounten.

`deployment/render.py: generate_secrets()` oppretter originalfilen med modus `0600`.
`write_file_archives()` oppretter selve arkivet med `0600`, men `normalize()` setter
vanlige filer inne i arkivet til `0644`. Dette er lokalt reprodusert med en syntetisk
session key. Faktiske rettigheter etter Podman-import er ikke verifisert her.
PVC-bruk alene er ikke et bekreftet sikkerhetshull; vurder tilgang og livssyklus,
ikke bare navnet på YAML-ressursen.

Identity deklarerer også `credentials/app/ApiResources__0__ApiSecrets__0__Value` og
leverer den via `identity-api-secrets` og `envFrom`. Gjennomgangen fant ingen bruk
av verdien i dagens Identity-kode. Bekreft dette før den fjernes.

### 2. Kartlegg før endring

Les `AGENTS.md` dersom den finnes, README, ARCHITECTURE og relevante tester.
Følg de faktiske filene gjennom:

- `components/app1/config.defaults.yaml` og tilsvarende for app2/identity.
- Komponentenes manifester og `scripts/generate-certificates.sh`.
- `deployment/render.py`: generering, filgrupper, Secret/PVC og importarkiver.
- `deployment/deploy.py`: installasjon, retry og avinstallasjon.
- `apps/todo-backend/app.py` og `apps/identity/Program.cs`.

Session key brukes som Flask `SECRET_KEY` til sesjonscookies. Den private
klientnøkkelen brukes til `private_key_jwt` mot Identity. Dette er forskjellige
hemmeligheter med forskjellige oppgaver; ingen av dem skal leveres til frontend.

### 3. Stram inn levering og rettigheter

Foretrekk å levere session key og privat klientnøkkel gjennom eksisterende
`SECRET_FILES`, som for databasepassord og Identitys signeringsnøkkel. Avklar at
valgt løsning støttes av målversjonen av Podman og eksisterende `.kube`-flyt.
En liten credential-gruppe per app er tilstrekkelig; ikke innfør et nytt rammeverk.

- Behold persistente originalfiler og samme bytes gjennom normale oppgraderinger,
  gjentatt installasjon og retry. Ikke regenerer eller roter nøkler ved flyttingen.
- Sørg for eksplisitte restriktive rettigheter for hemmelige filer i containeren,
  for eksempel `0400` eller `0600`, med eierskap som passer prosessen som leser dem.
  Verifiser at Podman faktisk anvender feltene; ikke anta Kubernetes-oppførsel.
- Behold skrivebeskyttet mount og tilgang bare i backend. Behold eksisterende
  filstier i containeren hvis dette gir den enkleste og tydeligste løsningen.
- Offentlige sertifikater kan følge samme beskyttede gruppe når det forenkler
  mounten; ikke skap ekstra abstraksjoner bare for å skille offentlige filer.
- Session key og privat klientnøkkel skal ikke samtidig bli liggende i et aktivt
  generert `VOLUME_FILES`-arkiv etter endringen.
- Ikke sett alle generelle importfiler til `0600` uten å vurdere offentlige
  payloads, katalogtilgang og containernes UID/GID. Dersom hemmeligheter fortsatt
  må leveres gjennom importarkiv, begrunn valget og bevar restriktive rettigheter.
- Bevar avinstallasjonens skille mellom å beholde state og eksplisitt
  `--delete-data`. Sletting skal fortsatt være avgrenset til valgt komponent.

En Secret gir ikke automatisk kryptering eller minnebasert lagring i Podman.
Renderet YAML med base64-kodede secrets er sensitiv. Beskytt YAML, originalfiler,
eventuelle arkiver og runtime-kopier, og unngå verdier i logger og testutskrifter.

### 4. Fjern ubrukt API-secret

Hvis kartleggingen bekrefter at API-secret-en er ubrukt, fjern dens generering,
Secret-deklarasjon, `envFrom`-referanse og eventuelle unødvendige katalogopprettelser.
Oppdater relevante tester og dokumentasjon. Ikke fjern legitime API-scopes,
klientsertifikatautentisering, databasepassord eller Identitys tokensignering.
Ingen automatisk sletting av ukjente eksisterende credential-filer.

### 5. Tester og dokumentasjon

Legg til målrettede tester som verifiserer:

- Riktig leveringsmåte, mount, eierskap/rettighetsinnstillinger og uendrede
  credential-bytes. Undersøk faktisk generert YAML og eventuelle arkivmedlemmer.
- Separate nøkler for app1 og app2 og ingen credential-mount i frontend.
- Ingen duplisert privat nøkkel/session key i appens genererte importarkiv.
- Installasjon, upgrade og retry beholder nøklene, samt fortsatt trygg og avgrenset
  avinstallasjon med og uten datasletting.
- Ubrukt API-secret genereres eller refereres ikke lenger.
- Private filer og bytecode følger fortsatt ikke med i offline-bundles.

Oppdater README og relevant test-/arkitekturdokumentasjon med faktisk filflyt og
skillet mellom en hemmelig verdi og YAML-typen `Secret`. Brukerens diagramskisser
er foreløpig til diskusjon; ikke legg dem inn uten egen avtale.

Kjør repoets dokumenterte produkttester, acceptance-harness-tester, ruff,
formatkontroll, pyright, vermin og shellcheck. Behold Python 3.6-kompatibilitet
for host-verktøyene. Oppdater berørte image-/releaseversjoner etter repoets
konvensjoner dersom endringen krever nye images; ikke gjenbruk en uforanderlig tag.

Beskriv eller utvid målrettet labverifikasjon av reelle filmoduser, lesetilgang,
innlogging, sesjoner etter restart/upgrade, klientautentisering og avinstallasjon.
Ikke start destruktive VM-/snapshot-kjøringer uten eksplisitt autorisasjon.
Skill mellom lokale tester, statisk vurdering og faktisk Podman-verifikasjon.

### 6. Avgrensning og leveranse

Ingen eksisterende installasjoner trenger migrering fra gamle layouts. Ikke bygg
migreringskode, fallback, automatisk nøkkelrotasjon eller en ny secret manager.
Normale oppgraderinger i den støttede modellen skal fortsatt bevare private filer
og data. Ikke redesign Flask-/OIDC-autentiseringen eller tilpass demoen til en
hypotetisk C#/GraphQL-applikasjon som del av denne oppgaven.

Rapporter valgt løsning, konkrete endringer, testresultater og hva som gjenstår i
lab. Forklar hvilke sikkerhetsegenskaper som faktisk er forbedret, uten å påstå at
et bytte fra PVC til Secret alene gir kryptering eller en ny isolasjonsgrense.

## 15. Remove obsolete legacy layout refusal checks

Status: implemented in 0.4.5; local checks and remaining target verification are
reported in [layout cleanup](acceptance/LEGACY-CHECK-CLEANUP.md). The original
agent message follows. No existing installations require migration.

Melding til agenten:

Fjern kontrollene som bare oppdager og avviser historisk core-layout eller
kombinert platform/Identity-layout i `gunstein/podman_offline`.
`core-identity-data` i `deployment/deploy.py` er ett konkret eksempel; dagens
Identity-volum heter `identity-data`. Det gamle navnet brukes til avvisning,
ikke som et aktivt databasevolum.

- Kartlegg `reject_legacy_layout()`, `reject_combined_platform()`,
  `legacy_volume_exists()` og tilsvarende kontroller i sertifikat-/dev-script,
  tester og aktive acceptance-scenarioer. Ta utgangspunkt i siste repo-status.
- Fjern avvisningskontrollene, tilhørende kall og feiltekster om separate
  migreringsprosedyrer. Ikke bare erstatt gamle volumnavn med nye navn i disse
  kontrollene; dagens volumer skal ikke avvises som historisk state.
- Oppdater tester og aktiv operatørdokumentasjon slik at de beskriver dagens
  støttede layout. Behold historiske rapporter, evidence og fixtures som
  eksplisitt representerer gamle releaser; forklar gjenværende gamle navn.
- Ikke innfør migrering, fallback, aliaser, kompatibilitetsgrener, automatisk
  opprydding eller sletting/flytting av gamle filer eller volumer. Oppgavene 4
  og 11 skal ikke implementeres; de er historiske forslag som er erstattet av
  presiseringen om at ingen eksisterende installasjoner trenger migrering.
- Behold normal oppgradering og retry i dagens komponentmodell: config,
  credentials og data skal fortsatt bevares. Behold database-preflight,
  avhengighets-/versjonskontroller, pending-state-validering, komponentisolasjon,
  sikre filstier/rettigheter og bundle-beskyttelse.

Kjør produkttester, acceptance-harness-tester og repoets relevante ruff-, format-,
pyright-, vermin- og shellcheck-kontroller samt `git diff --check`. Behold Python
3.6-kompatibilitet for host-verktøyene. Rapporter hva som er fjernet, hvilke
historiske referanser som er beholdt, testresultater og eventuelle labhull.

## 16. Combine secret generation and file delivery declarations

Status: planned, separate config simplification. Coordinate with item 14 using
the actual repository state; this task does not choose a new delivery mechanism.

Melding til agenten:

Forenkle config-modellen i `gunstein/podman_offline` slik at eventuell generering
deklareres sammen med filene som leveres gjennom `SECRET_FILES` eller
`VOLUME_FILES`. Fjern behovet for en separat `GENERATED_SECRETS`-liste og dobbelt
vedlikehold av samme filsti. Målet er at en middels erfaren utvikler enkelt skal
forstå både hvor en fil kommer fra og hvordan den leveres til containeren.

Et mulig format, som et utgangspunkt for vurdering, er:

```yaml
SECRET_FILES:
  app2-database-password:
    directory: credentials/database
    generate:
    - password
  identity-signing:
    directory: credentials/identity
```

Her er `generate` relativt til den deklarerte katalogen og angir bare filer som
skal opprettes hvis de mangler. Uten `generate` brukes eksisterende filer.
Støtt samme prinsipp for `VOLUME_FILES`, siden genererte sesjonsnøkler i dagens
modell leveres gjennom volumer. Undersøk om formatet bør bruke en liste med
filkilder fremfor én `directory`, slik at nødvendig støtte for flere kildefiler
og kataloger ikke forsvinner. Velg én enkel og konsekvent modell; ikke innfør et
generelt generator-/pluginrammeverk eller to parallelle config-formater.

- Les gjeldende defaults, config-validering, generering, rendering, database-
  preflight, bundling, dev-/sertifikatscript og tester før formatet bestemmes.
- Behold dagens genereringsregler og tidspunkt: bare eksplisitt deklarerte
  manglende filer opprettes der dette er tillatt. Eksisterende gyldige filer
  beholdes byte-for-byte; tomme/ugyldige filer gir feil. Manglende databasepassord
  med eksisterende databasevolum skal fortsatt avvises før generering.
- Sertifikater og private signeringsnøkler skal fortsatt forberedes separat.
  Den nye deklarasjonen skal ikke gjøre deploy til en sertifikatutsteder.
- Behold credential-stier, Secret-navn og keys, volum-/PVC-navn, container-mounts,
  passordformat/-lengde, config-precedence og autoritativ persistent config.
  Behold sikre filstier, symlink-kontroller og private fil-/katalogrettigheter.
- Bundle-beskyttelsen må fortsatt følge deklarerte private filer, inkludert
  symlink-aliaser, og ikke bare filtrere på katalog- eller filnavn. Credentials
  og komplette connection strings skal ikke eksponeres i logger eller bundles.
- Oppdater alle aktive configs, eksempler, hjelpere, tester og dokumentasjon til
  den nye deklarasjonen. Behold historiske rapporter og eksplisitte historiske
  release-fixtures. Ingen eksisterende installasjoner trenger config-migrering:
  ikke lag migreringskode, fallback, aliaser eller støtte for gammelt format.

Legg til målrettet dekning av genererte og eksternt leverte filer, begge
leveringsmåter, ugyldige deklarasjoner/stier, config-initialisering, database-
preflight, byte-bevaring ved restart/redeploy/retry og bundle-beskyttelse.
Behold config, credentials og data ved normale oppgraderinger i den nye modellen.
Ikke kombiner med passordrotasjon, endret komponentarkitektur eller bred
modulrefaktorering.

Kjør produkttester, acceptance-harness-tester og relevante ruff-, format-,
pyright-, vermin- og shellcheck-kontroller samt `git diff --check`. Behold Python
3.6-kompatibilitet for host-verktøyene. Rapporter valgt format, endrede filer,
testresultater og hva som eventuelt gjenstår å verifisere i lab.

## 17. Use an init container for database preparation in one demo app

Status: planned. At least one actual demo app must use an init container;
the standalone `examples/init-containers` example is not sufficient.

Melding til agenten:

La én av appene i `gunstein/podman_offline` bruke `initContainers` til reell
databaseklargjøring før backend starter. Velg og begrunn en egnet app ut fra
gjeldende kode og manifests, fortrinnsvis app1 eller app2. Dagens Todo-backend
oppretter tabellen i oppstartskoden, mens Identity klargjør brukertabellen selv.
Flytt et konkret, nødvendig klargjøringssteg til init-containeren; ikke legg til
en symbolsk init-container som bare kjører `echo` eller en ventekommando.

- Undersøk Podman/Quadlet-oppstarten og hvor PostgreSQL kjører før løsningen
  velges. En init-container må ikke vente på en ordinær databasecontainer i
  samme pod som først starter etter init-containeren. Dokumenter hvordan
  databasen faktisk blir tilgjengelig før klargjøringssteget kjører.
- Backend skal starte først etter vellykket init. Databaseventing skal være
  tidsbegrenset, og init-feil skal gi en tydelig feil uten å eksponere passord
  eller komplette connection strings. Bruk appens eksisterende credential-
  mekanisme og samme databasepassord som databasen og backend.
- Klargjøringen skal være idempotent: fersk installasjon oppretter nødvendig
  skjema; restart, redeploy og retry bevarer eksisterende databaseinnhold og
  credentials. Ikke innfør passordrotasjon, destruktive resets, migrering fra
  historiske layouts eller et generelt database-migreringsrammeverk.
- Behold den andre appens virkemåte. Appene deler backend-kilde/image i dagens
  modell; unngå utilsiktet å kreve init-klargjøring også i appen som ikke endres.
  Behold isolasjon fra platform, identity og sibling-appens data og tjenester.
- Oppdater nødvendig appkode, manifests, dev-flyt, bundling, tester og README.
  Offline-bundlen skal inneholde alle nødvendige images; ingen nedlasting av
  kode eller pakker ved init. Følg repoets regler for nye image-/releaseversjoner.

Legg til målrettede tester for oppstartsrekkefølge, init-feil, tidsavbrudd og
gjentatt klargjøring uten datatap. Kjør produkttester, acceptance-harness-tester
og relevante lint-, format-, type-, kompatibilitets- og shellkontroller samt
`git diff --check`. Behold Python 3.6-kompatibilitet for host-verktøyene.
Beskriv nødvendig labverifikasjon av faktisk Podman-oppførsel, inkludert fersk
installasjon og restart med beholdte data. Ikke påstå at stubbede tester beviser
reell init-container-rekkefølge. Rapporter valgt app, konkret flyt, endrede filer,
testresultater og verifikasjonshull.

## 18. Extract app image building into Python and use stock nginx for proxy

Status: planned. Separate build/manifest cleanup; no implementation performed.

Melding til agenten:

Skill ut koden som bygger demoappene under `apps/` til en egen Python-fil i
`gunstein/podman_offline`. Fjern samtidig behovet for å bygge et eget proxy-image:
platform skal referere et versjonert standard nginx-image direkte, og alt som
trengs for proxyens konfigurasjon/oppstart skal deklareres i manifest-YAML.
Behold eksisterende komponentarkitektur, CLI og offline installasjonsmodell.

### 1. Les eksisterende flyt

Les `AGENTS.md` dersom den finnes, README, ARCHITECTURE, BACKLOG og relevante
tester. Undersøk minst `dev/build-images.sh`, `dev/pull-images.sh`,
`bundle.py: manifest_images()` / image-validering / arkivering,
`apps/*/Containerfile`, `apps/proxy/default.conf`, `15-resolver.envsh`,
platform-manifestene, ruteregistreringene og image-/registry-acceptance-hjelperne.
Funksjonsnavn og filer kan ha endret seg; bruk faktisk gjeldende repo-status.

### 2. Egen Python-fil for image-bygging

- Flytt image-utvalg, validering og byggekommandoer fra shell til en liten,
  forståelig Python-fil, for eksempel `dev/build_images.py`. Behold
  `./dev/build-images.sh` som en tynn wrapper som bruker `python3 -B`.
- Bruk manifestenes faktiske, entydige image-referanser som kilde til hvilke
  demo-images som skal bygges, og hvilke tags de får. Gjenbruk eksisterende
  image-discovery/validering uten sirkulære imports eller duplisert image-liste.
- Behold dagens skille: bygg lokale demoapp-images med passende Containerfile
  og build context; registry-images hentes gjennom eksisterende pull-flyt.
  Behold PostgreSQLs eksplisitte upstream-pull/lokale tag dersom dette fortsatt
  er gjeldende modell. Ikke innfør skjult bygging som fallback ved pull-feil.
- Stopp tydelig ved ukjent lokal build-oppskrift, ugyldig referanse eller feilet
  Podman-kommando. Behold feilkoder og unngå shell-interpolering av argumenter.
- Ingen bygging eller andre handlinger ved import. Wrapper og Python-entrypoint
  skal finne repoet korrekt også fra en annen arbeidsmappe, uten bytecode-filer.
  Bruk Python 3.6-kompatibel kode og eksisterende avhengigheter.

### 3. Proxy uten eget image-bygg

- Erstatt `localhost/myproduct-proxy:...` med et fullt kvalifisert, eksplisitt
  versjonert standard nginx-image i platform-manifestet. Ikke bruk `latest`.
  Undersøk dagens baseimage og unngå en unødvendig nginx-versjonsendring.
- Flytt nødvendig nginx-konfigurasjon, template og eventuell liten oppstartskode
  inn i YAML, for eksempel ConfigMap-data og eksplisitt command/args eller det
  valgte imagets støttede entrypoint-mekanisme. Det skal ikke kreves et nytt
  image, proxy-Containerfile eller separate proxy-konfigurasjons-/scriptfiler i
  `apps/proxy/`. Fjern disse når aktive avhengigheter er erstattet.
- Behold runtime DNS fra containerens `/etc/resolv.conf` og dynamisk oppslag av
  komponentnavn. Platform må kunne starte uten appene/Identity, og routes skal
  fungere når tjenester kommer til eller restartes med nye adresser.
- Behold HTTPS_PORT, TLS-filer, begrensninger, `/livez`, ukjent-route 404 og
  `/routes/installed.conf`. Ikke hardkod app-/Identity-ruter i proxyens grunnconfig.
  Behold TLS-mount, rutemount, readOnly, hostname, hostIP/port og healthcheck.
- Respekter rendererens eksisterende hele-verdi-`@@...@@`-kontrakt. Hvis nginx-
  templating skjer ved containeroppstart, begrens variabelsubstitusjon slik at
  nginx-variabler i konfigurasjon/ruter ikke utilsiktet erstattes. Ikke innfør en
  generell endring av deploy-rendereren for å løse proxy-templating.
- Verifiser nødvendig shell/verktøystøtte, ConfigMap-mounts, filmoduser og
  oppstartsrekkefølge for faktisk valgt image og Podman-versjon. Ikke skriv til
  skrivebeskyttede mounts; kjør nginx som hovedprosess med korrekt signalhåndtering.

### 4. Offline, tester og dokumentasjon

Det nye nginx-imaget skal oppdages fra manifestet, hentes på byggemaskinen via
pull-flyten, arkiveres med platform-bundlen og lastes/verifiseres før installasjon.
Behold `imagePullPolicy: Never` på målmaskinen, checksums, image-navnvalidering og
isolasjon mellom bundles. Produksjon skal ikke hente images eller pakker fra nett.
Oppdater dev-/acceptance-hjelpere som fortsatt forventer egen proxy-build eller
filene under `apps/proxy`. Ikke endre historiske rapporter eller pinned fixtures.

Legg til målrettede tester for Python-entrypoint/wrapper fra annen arbeidsmappe,
korrekte manifest-tags/build contexts, deduplisering, build-/pull-feil og ingen
build av nginx. Verifiser renderet proxy-YAML, runtime-templating/DNS, bevarte
nginx-variabler, image-inkludering i offline-bundle og uendrede TLS-/rutemounts.
Oppdater tester som tidligere leste `apps/proxy/default.conf`, uten å svekke
kontrollene for separate komponenter og dynamiske ruteregistreringer.

Kjør produkttester, acceptance-harness-tester, ruff, formatkontroll, pyright,
vermin, shellcheck og `git diff --check` med repoets oppsett. Oppdater relevante
releaseversjoner etter repoets regler, uten å endre uendrede app-images/tags.
Dokumenter ny byggeflyt og hvordan proxyen konfigureres fra YAML. Beskriv nødvendig
labverifikasjon av HTTPS, innlogging, platform/help uten Identity, app-tillegg,
DNS etter restart, helse og offline installasjon. Ikke reset labmiljøer uten
autorisasjon og ikke påstå at stubbede tester beviser faktisk nginx/Podman-atferd.

Ingen config-/credential-migrering, fallback for gammel proxy-layout,
passordrotasjon, ny komponentmodell eller bred deploy-refaktorering. Behold
persistente config-/credential-bytes, databasedata, retry og SELinux-/fapolicyd-
kontroller. Rapporter endrede filer, valgt YAML-/entrypoint-løsning, faktiske
testresultater og verifikasjonshull.
