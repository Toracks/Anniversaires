// ============================================================================
// État global de l'application
// ============================================================================
let anniversaires = [];       // liste chargée depuis l'API
let dateReference = new Date(); // date "curseur" utilisée pour la navigation
let vueActuelle = 'month';    // 'month' | 'week' | 'day'

const MOIS_FR = ['Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
  'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'];
const JOURS_FR = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche'];

// ============================================================================
// Petit wrapper autour de fetch() : si la session a expiré (401), on renvoie
// directement vers la page de connexion plutôt que de laisser planter le JS.
// ============================================================================
async function apiFetch(url, options = {}) {
  const reponse = await fetch(url, options);
  if (reponse.status === 401) {
    window.location.href = '/login';
    return null;
  }
  return reponse;
}

// ============================================================================
// Chargement des données depuis l'API Flask
// ============================================================================
async function chargerAnniversaires() {
  const reponse = await apiFetch('/api/anniversaires');
  if (!reponse) return;
  anniversaires = await reponse.json();
  render();
}

// Renvoie la liste des anniversaires tombant un jour/mois donné (toutes années confondues)
function anniversairesDuJour(jour, mois) {
  return anniversaires.filter(a => a.jour === jour && a.mois === mois);
}

// ============================================================================
// Rendu général : dispatch selon la vue active
// ============================================================================
function render() {
  document.getElementById('vueMois').style.display = vueActuelle === 'month' ? '' : 'none';
  document.getElementById('vueSemaine').style.display = vueActuelle === 'week' ? '' : 'none';
  document.getElementById('vueJour').style.display = vueActuelle === 'day' ? '' : 'none';

  document.querySelectorAll('.view-toggle button').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.view === vueActuelle);
  });

  if (vueActuelle === 'month') renderMois();
  else if (vueActuelle === 'week') renderSemaine();
  else renderJour();
}

// ============================================================================
// Vue MOIS
// ============================================================================
function renderMois() {
  const annee = dateReference.getFullYear();
  const mois = dateReference.getMonth(); // 0-indexé

  document.getElementById('periodLabel').textContent = `${MOIS_FR[mois]} ${annee}`;

  const premierJourMois = new Date(annee, mois, 1);
  // getDay() renvoie 0 pour dimanche ; on veut lundi en premier donc on décale
  let decalage = premierJourMois.getDay() - 1;
  if (decalage < 0) decalage = 6;

  const nbJoursMois = new Date(annee, mois + 1, 0).getDate();
  const nbJoursMoisPrecedent = new Date(annee, mois, 0).getDate();

  const aujourdHui = new Date();
  const grid = document.getElementById('monthGrid');
  grid.innerHTML = '';

  const totalCases = Math.ceil((decalage + nbJoursMois) / 7) * 7;

  for (let i = 0; i < totalCases; i++) {
    const numeroJour = i - decalage + 1;
    let jourReel, moisReel, anneeReel, horsMois;

    if (numeroJour < 1) {
      jourReel = nbJoursMoisPrecedent + numeroJour;
      moisReel = mois === 0 ? 12 : mois;
      anneeReel = mois === 0 ? annee - 1 : annee;
      horsMois = true;
    } else if (numeroJour > nbJoursMois) {
      jourReel = numeroJour - nbJoursMois;
      moisReel = mois === 11 ? 1 : mois + 2;
      anneeReel = mois === 11 ? annee + 1 : annee;
      horsMois = true;
    } else {
      jourReel = numeroJour;
      moisReel = mois + 1;
      anneeReel = annee;
      horsMois = false;
    }

    const cell = document.createElement('div');
    cell.className = 'day-cell' + (horsMois ? ' outside' : '');

    const estAujourdHui = !horsMois && jourReel === aujourdHui.getDate()
      && (mois + 1) === (aujourdHui.getMonth() + 1) && annee === aujourdHui.getFullYear();
    if (estAujourdHui) cell.classList.add('today');

    const entries = anniversairesDuJour(jourReel, moisReel);

    const numDiv = document.createElement('div');
    numDiv.className = 'day-number';
    numDiv.textContent = jourReel;
    cell.appendChild(numDiv);

    if (entries.length > 0) {
      const entriesDiv = document.createElement('div');
      entriesDiv.className = 'day-entries';
      entries.slice(0, 2).forEach(a => {
        const chip = document.createElement('div');
        chip.className = 'entry-chip';
        chip.innerHTML = `<span class="glow"></span><span class="label">${a.prenom}</span>`;
        entriesDiv.appendChild(chip);
      });
      if (entries.length > 2) {
        const more = document.createElement('div');
        more.className = 'entry-more';
        more.textContent = `+${entries.length - 2} autre(s)`;
        entriesDiv.appendChild(more);
      }
      cell.appendChild(entriesDiv);
    }

    cell.addEventListener('click', () => ouvrirDetailJour(jourReel, moisReel, anneeReel));
    grid.appendChild(cell);
  }
}

// ============================================================================
// Vue SEMAINE
// ============================================================================
function renderSemaine() {
  // Trouver le lundi de la semaine contenant dateReference
  const d = new Date(dateReference);
  let decalage = d.getDay() - 1;
  if (decalage < 0) decalage = 6;
  const lundi = new Date(d);
  lundi.setDate(d.getDate() - decalage);

  const dimanche = new Date(lundi);
  dimanche.setDate(lundi.getDate() + 6);

  document.getElementById('periodLabel').textContent =
    `${lundi.getDate()} ${MOIS_FR[lundi.getMonth()].slice(0, 3)} – ${dimanche.getDate()} ${MOIS_FR[dimanche.getMonth()].slice(0, 3)}`;

  const grid = document.getElementById('weekGrid');
  grid.innerHTML = '';
  const aujourdHui = new Date();

  for (let i = 0; i < 7; i++) {
    const jourDate = new Date(lundi);
    jourDate.setDate(lundi.getDate() + i);

    const col = document.createElement('div');
    col.className = 'week-col';

    const estAujourdHui = jourDate.toDateString() === aujourdHui.toDateString();
    if (estAujourdHui) col.classList.add('today');

    const head = document.createElement('div');
    head.className = 'week-col-head';
    head.textContent = `${JOURS_FR[i].slice(0, 3)} ${jourDate.getDate()}`;
    col.appendChild(head);

    const entries = anniversairesDuJour(jourDate.getDate(), jourDate.getMonth() + 1);
    entries.forEach(a => {
      const chip = document.createElement('div');
      chip.className = 'entry-chip';
      chip.style.marginBottom = '4px';
      chip.innerHTML = `<span class="glow"></span><span class="label">${a.prenom}</span>`;
      col.appendChild(chip);
    });

    col.addEventListener('click', () => ouvrirDetailJour(jourDate.getDate(), jourDate.getMonth() + 1, jourDate.getFullYear()));
    grid.appendChild(col);
  }
}

// ============================================================================
// Vue JOUR
// ============================================================================
function renderJour() {
  const jour = dateReference.getDate();
  const mois = dateReference.getMonth() + 1;
  const annee = dateReference.getFullYear();

  document.getElementById('periodLabel').textContent =
    `${JOURS_FR[(dateReference.getDay() + 6) % 7]} ${jour} ${MOIS_FR[mois - 1]} ${annee}`;

  const entries = anniversairesDuJour(jour, mois);
  const container = document.getElementById('dayView');
  container.innerHTML = '';

  if (entries.length === 0) {
    container.innerHTML = '<div class="day-view-empty">Aucun anniversaire ce jour-là.</div>';
    return;
  }

  entries.forEach(a => container.appendChild(creerLignePersonne(a)));
}

// Construit une ligne "personne" réutilisée dans la vue jour et le panneau détail
function creerLignePersonne(a) {
  const row = document.createElement('div');
  row.className = 'person-row';

  const nomComplet = a.nom ? `${a.prenom} ${a.nom}` : a.prenom;
  let sousTexte = `${String(a.jour).padStart(2, '0')}/${String(a.mois).padStart(2, '0')}`;
  if (a.annee) {
    const age = new Date().getFullYear() - a.annee;
    sousTexte += `/${a.annee} · ${age} ans`;
  }
  if (a.heure) sousTexte += ` · ${a.heure}`;

  const info = document.createElement('div');
  info.className = 'person-info';
  info.innerHTML = `<strong>${nomComplet}</strong><div class="sub">${sousTexte}</div>`;

  const actions = document.createElement('div');
  actions.className = 'person-actions';

  const btnModifier = document.createElement('button');
  btnModifier.textContent = 'Modifier';
  btnModifier.addEventListener('click', (e) => { e.stopPropagation(); ouvrirFormulaire(a); });

  const btnSupprimer = document.createElement('button');
  btnSupprimer.textContent = 'Supprimer';
  btnSupprimer.addEventListener('click', (e) => { e.stopPropagation(); supprimerAnniversaire(a.id); });

  actions.appendChild(btnModifier);
  actions.appendChild(btnSupprimer);

  row.appendChild(info);
  row.appendChild(actions);
  return row;
}

// ============================================================================
// Panneau détail d'un jour (ouvert au clic sur une case du mois/semaine)
// ============================================================================
let jourSelectionne = null; // { jour, mois, annee }

function ouvrirDetailJour(jour, mois, annee) {
  jourSelectionne = { jour, mois, annee };
  const entries = anniversairesDuJour(jour, mois);

  document.getElementById('detailTitre').textContent =
    `${String(jour).padStart(2, '0')}/${String(mois).padStart(2, '0')}`;

  const contenu = document.getElementById('detailContenu');
  contenu.innerHTML = '';

  if (entries.length === 0) {
    contenu.innerHTML = '<div class="day-view-empty">Aucun anniversaire ce jour-là.</div>';
  } else {
    entries.forEach(a => contenu.appendChild(creerLignePersonne(a)));
  }

  document.getElementById('overlayDetail').classList.remove('hidden');
}

document.getElementById('btnFermerDetail').addEventListener('click', () => {
  document.getElementById('overlayDetail').classList.add('hidden');
});

document.getElementById('btnAjouterDepuisDetail').addEventListener('click', () => {
  document.getElementById('overlayDetail').classList.add('hidden');
  const prefill = jourSelectionne
    ? { jour: jourSelectionne.jour, mois: jourSelectionne.mois }
    : null;
  ouvrirFormulaire(null, prefill);
});

// ============================================================================
// Formulaire ajout / modification
// ============================================================================
function ouvrirFormulaire(anniversaire = null, prefill = null) {
  const form = document.getElementById('formAnniversaire');
  form.reset();
  document.getElementById('formErreur').textContent = '';

  if (anniversaire) {
    document.getElementById('formTitre').textContent = 'Modifier l\'anniversaire';
    document.getElementById('fId').value = anniversaire.id;
    document.getElementById('fPrenom').value = anniversaire.prenom;
    document.getElementById('fNom').value = anniversaire.nom || '';
    document.getElementById('fDateTexte').value =
      `${String(anniversaire.jour).padStart(2, '0')}/${String(anniversaire.mois).padStart(2, '0')}` +
      (anniversaire.annee ? `/${anniversaire.annee}` : '');
    document.getElementById('fAnnee').value = anniversaire.annee || '';
    document.getElementById('fHeure').value = anniversaire.heure || '';
  } else {
    document.getElementById('formTitre').textContent = 'Ajouter un anniversaire';
    document.getElementById('fId').value = '';
    if (prefill) {
      document.getElementById('fDateTexte').value =
        `${String(prefill.jour).padStart(2, '0')}/${String(prefill.mois).padStart(2, '0')}`;
    }
  }

  document.getElementById('overlayForm').classList.remove('hidden');
  document.getElementById('fPrenom').focus();
}

document.getElementById('btnAjouter').addEventListener('click', () => ouvrirFormulaire());
document.getElementById('btnAnnulerForm').addEventListener('click', () => {
  document.getElementById('overlayForm').classList.add('hidden');
});

// Bouton "calendrier" à côté du champ texte : ouvre le sélecteur natif
document.getElementById('btnOuvrirPicker').addEventListener('click', () => {
  const picker = document.getElementById('fDatePicker');
  picker.showPicker ? picker.showPicker() : picker.click();
});

// Quand une date est choisie via le sélecteur natif, on remplit le champ texte + année
document.getElementById('fDatePicker').addEventListener('change', (e) => {
  const [an, mo, jr] = e.target.value.split('-');
  document.getElementById('fDateTexte').value = `${jr}/${mo}/${an}`;
  document.getElementById('fAnnee').value = an;
});

// Parse le champ texte JJ/MM ou JJ/MM/AAAA -> { jour, mois, annee|null }
function parserDateTexte(texte) {
  const parties = texte.trim().split('/');
  if (parties.length < 2) return null;

  const jour = parseInt(parties[0], 10);
  const mois = parseInt(parties[1], 10);
  const annee = parties[2] ? parseInt(parties[2], 10) : null;

  if (isNaN(jour) || isNaN(mois) || jour < 1 || jour > 31 || mois < 1 || mois > 12) return null;

  return { jour, mois, annee };
}

document.getElementById('formAnniversaire').addEventListener('submit', async (e) => {
  e.preventDefault();
  const erreurEl = document.getElementById('formErreur');
  erreurEl.textContent = '';

  const prenom = document.getElementById('fPrenom').value.trim();
  const dateParsee = parserDateTexte(document.getElementById('fDateTexte').value);
  const anneeChamp = document.getElementById('fAnnee').value;

  if (!prenom) {
    erreurEl.textContent = 'Le prénom est obligatoire.';
    return;
  }
  if (!dateParsee) {
    erreurEl.textContent = 'Date invalide. Utilise le format JJ/MM ou JJ/MM/AAAA.';
    return;
  }

  const id = document.getElementById('fId').value;
  const payload = {
    prenom,
    nom: document.getElementById('fNom').value.trim(),
    jour: dateParsee.jour,
    mois: dateParsee.mois,
    annee: anneeChamp ? parseInt(anneeChamp, 10) : (dateParsee.annee || null),
    heure: document.getElementById('fHeure').value,
  };

  try {
    const url = id ? `/api/anniversaires/${id}` : '/api/anniversaires';
    const methode = id ? 'PUT' : 'POST';
    const reponse = await apiFetch(url, {
      method: methode,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!reponse) return;

    if (!reponse.ok) {
      const err = await reponse.json();
      erreurEl.textContent = err.erreur || 'Une erreur est survenue.';
      return;
    }

    document.getElementById('overlayForm').classList.add('hidden');
    await chargerAnniversaires();
  } catch (err) {
    erreurEl.textContent = 'Impossible de contacter le serveur.';
  }
});

async function supprimerAnniversaire(id) {
  if (!confirm('Supprimer cet anniversaire ?')) return;
  const reponse = await apiFetch(`/api/anniversaires/${id}`, { method: 'DELETE' });
  if (!reponse) return;
  document.getElementById('overlayDetail').classList.add('hidden');
  await chargerAnniversaires();
}

// ============================================================================
// Navigation (précédent / suivant / aujourd'hui) + changement de vue
// ============================================================================
document.getElementById('btnPrev').addEventListener('click', () => {
  if (vueActuelle === 'month') dateReference.setMonth(dateReference.getMonth() - 1);
  else if (vueActuelle === 'week') dateReference.setDate(dateReference.getDate() - 7);
  else dateReference.setDate(dateReference.getDate() - 1);
  render();
});

document.getElementById('btnNext').addEventListener('click', () => {
  if (vueActuelle === 'month') dateReference.setMonth(dateReference.getMonth() + 1);
  else if (vueActuelle === 'week') dateReference.setDate(dateReference.getDate() + 7);
  else dateReference.setDate(dateReference.getDate() + 1);
  render();
});

document.getElementById('btnAujourdhui').addEventListener('click', () => {
  dateReference = new Date();
  render();
});

document.querySelectorAll('.view-toggle button').forEach(btn => {
  btn.addEventListener('click', () => {
    vueActuelle = btn.dataset.view;
    render();
  });
});

// ============================================================================
// Recherche par prénom (filtrage côté client sur les données déjà chargées)
// ============================================================================
const rechercheInput = document.getElementById('rechercheInput');
const rechercheResultats = document.getElementById('rechercheResultats');

rechercheInput.addEventListener('input', () => {
  const terme = rechercheInput.value.trim().toLowerCase();
  if (!terme) {
    rechercheResultats.classList.add('hidden');
    return;
  }

  const resultats = anniversaires.filter(a => a.prenom.toLowerCase().includes(terme));
  rechercheResultats.innerHTML = '';

  if (resultats.length === 0) {
    rechercheResultats.innerHTML = '<div class="search-empty">Aucun résultat.</div>';
  } else {
    resultats.forEach(a => {
      const item = document.createElement('div');
      const nomComplet = a.nom ? `${a.prenom} ${a.nom}` : a.prenom;
      item.innerHTML = `<span>${nomComplet}</span><span class="muted">${String(a.jour).padStart(2, '0')}/${String(a.mois).padStart(2, '0')}</span>`;
      item.addEventListener('click', () => {
        dateReference = new Date(dateReference.getFullYear(), a.mois - 1, a.jour);
        vueActuelle = 'month';
        rechercheResultats.classList.add('hidden');
        rechercheInput.value = '';
        render();
        setTimeout(() => ouvrirDetailJour(a.jour, a.mois, dateReference.getFullYear()), 150);
      });
      rechercheResultats.appendChild(item);
    });
  }

  rechercheResultats.classList.remove('hidden');
});

document.addEventListener('click', (e) => {
  if (!e.target.closest('.search-wrap')) rechercheResultats.classList.add('hidden');
});

// ============================================================================
// Démarrage
// ============================================================================
chargerAnniversaires();