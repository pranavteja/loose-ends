import { ConnectionState, Room, RoomEvent, Track } from 'livekit-client';
import './styles.css';

const connectButton = document.querySelector('#connect-button');
const connectionPill = document.querySelector('#connection-pill');
const statusText = document.querySelector('#conversation-status');
const voicePresence = document.querySelector('#voice-presence');
const sessionStateTitle = document.querySelector('#session-state-title');
const sessionStateCopy = document.querySelector('#session-state-copy');
const audioOutput = document.querySelector('#audio-output');
const reviewCount = document.querySelector('#review-count');
const draftHandoff = document.querySelector('#draft-handoff');
const draftHandoffTitle = document.querySelector('#draft-handoff-title');
const draftHandoffCopy = document.querySelector('#draft-handoff-copy');
const reviewEmpty = document.querySelector('#review-empty');
const reviewWorkspace = document.querySelector('#review-workspace');
const draftList = document.querySelector('#draft-list');
const draftListCount = document.querySelector('#draft-list-count');
const reviewForm = document.querySelector('#review-form');
const proposalKind = document.querySelector('#proposal-kind');
const proposalTiming = document.querySelector('#proposal-timing');
const proposalTitle = document.querySelector('#proposal-title');
const proposalDescription = document.querySelector('#proposal-description');
const proposalDueDate = document.querySelector('#proposal-due-date');
const proposalWorkTime = document.querySelector('#proposal-work-time');
const proposalSteps = document.querySelector('#proposal-steps');
const proposalSource = document.querySelector('#proposal-source');
const proposalMissing = document.querySelector('#proposal-missing');
const approveProposalButton = document.querySelector('#approve-proposal');
const dismissProposalButton = document.querySelector('#dismiss-proposal');
const boardEmpty = document.querySelector('#board-empty');
const boardContent = document.querySelector('#board-content');
const toast = document.querySelector('#toast');

let room = null;
let agentParticipant = null;
let attachedAudio = new Map();
let processedAssistantSegments = new Set();
let reviewProposals = [];
let selectedProposalId = null;
let toastTimer = null;

function escapeHtml(value = '') {
  return String(value).replace(/[&<>'"]/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#039;', '"': '&quot;',
  }[character]));
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data.detail;
    throw new Error(typeof detail === 'string' ? detail : detail?.message || 'Something went wrong. Please try again.');
  }
  return data;
}

function showToast(message, tone = 'success') {
  window.clearTimeout(toastTimer);
  toast.textContent = message;
  toast.dataset.tone = tone;
  toast.hidden = false;
  toastTimer = window.setTimeout(() => { toast.hidden = true; }, 4200);
}

async function showView(viewName, { updateHash = true } = {}) {
  const safeView = ['talk', 'review', 'board'].includes(viewName) ? viewName : 'talk';
  document.querySelectorAll('.app-view').forEach((view) => {
    view.hidden = view.dataset.view !== safeView;
  });
  document.querySelectorAll('.nav-item').forEach((item) => {
    const active = item.dataset.viewTarget === safeView;
    item.classList.toggle('is-active', active);
    if (active) item.setAttribute('aria-current', 'page');
    else item.removeAttribute('aria-current');
  });
  if (updateHash) history.replaceState(null, '', `#${safeView}`);
  window.scrollTo({ top: 0, behavior: 'smooth' });

  try {
    if (safeView === 'review') await refreshReview();
    if (safeView === 'board') await refreshBoard();
  } catch (error) {
    showToast(error.message, 'error');
  }
}

document.querySelectorAll('[data-view-target]').forEach((button) => {
  button.addEventListener('click', () => showView(button.dataset.viewTarget));
});

function setStatus(status, detail) {
  document.body.dataset.voiceState = status;
  connectionPill.dataset.status = status;
  voicePresence.dataset.status = status;
  const labels = {
    offline: 'Not connected', connecting: 'Connecting…', listening: 'Listening',
    thinking: 'Thinking…', speaking: 'Speaking', error: 'Needs attention',
  };
  const titles = {
    offline: 'Ready when you are', connecting: 'Opening your private room',
    listening: 'I’m listening', thinking: 'Working that through',
    speaking: 'Loose Ends is speaking', error: 'The room needs attention',
  };
  const copies = {
    offline: 'Start the room, then talk exactly as you would to a thoughtful planning partner.',
    connecting: 'Connecting your microphone and bringing the planning companion into the room.',
    listening: 'Take your time. Pause naturally, or start speaking to interrupt the response.',
    thinking: 'Your thought is being understood and shaped into a useful next question.',
    speaking: 'You can speak over the response at any time—your voice takes priority.',
    error: 'Check the local voice setup and try starting the conversation again.',
  };
  connectionPill.textContent = labels[status] || labels.offline;
  sessionStateTitle.textContent = titles[status] || titles.offline;
  sessionStateCopy.textContent = detail || copies[status] || copies.offline;
  statusText.textContent = detail || {
    offline: 'One tap to begin · You can interrupt at any time',
    connecting: 'Warming up a private voice room…',
    listening: 'I’m listening. Take your time.',
    thinking: 'Shaping that into something useful…',
    speaking: 'Loose Ends is responding — speak to interrupt.',
    error: 'Check your local voice setup, then try again.',
  }[status];
}

function attachRemoteAudio(track, publication) {
  if (track.kind !== Track.Kind.Audio) return;
  const element = track.attach();
  element.autoplay = true;
  audioOutput.append(element);
  attachedAudio.set(publication.trackSid, element);
}

function detachRemoteAudio(track, publication) {
  if (track.kind !== Track.Kind.Audio) return;
  attachedAudio.get(publication.trackSid)?.remove();
  attachedAudio.delete(publication.trackSid);
  track.detach();
}

function agentStateChanged(participant) {
  if (participant) {
    agentParticipant = participant;
  }
  const state = participant.attributes?.['lk.agent.state'];
  if (state && ['listening', 'thinking', 'speaking'].includes(state)) setStatus(state);
}

function agentConnected(participant) {
  if (!participant) return;
  agentParticipant = participant;
  agentStateChanged(participant);
}

function agentDisconnected(participant) {
  if (participant?.identity !== agentParticipant?.identity) return;
  agentParticipant = null;
  if (room) setStatus('connecting', 'The planning companion is reconnecting…');
}

async function receiveTranscript(reader, participant) {
  let message;
  try {
    message = await reader.readAll();
  } catch (error) {
    console.error('Transcript stream ended early', error);
    return;
  }
  const attributes = reader.info.attributes || {};
  const isTrackTranscript = Boolean(attributes['lk.transcribed_track_id']);
  const segmentId = attributes['lk.segment_id'] || reader.info.id || crypto.randomUUID();
  const isFinal = isTrackTranscript ? attributes['lk.transcription_final'] === 'true' : true;
  const role = participant?.identity === room?.localParticipant.identity ? 'user' : 'assistant';
  if (role === 'user' && isFinal) {
    setStatus('thinking');
  }
  if (role === 'assistant' && isFinal) {
    if (!message?.trim() || processedAssistantSegments.has(segmentId)) return;
    processedAssistantSegments.add(segmentId);
    window.setTimeout(() => refreshReview({ quiet: true }), 700);
  }
}

function wireRoom(nextRoom) {
  nextRoom.on(RoomEvent.ConnectionStateChanged, (state) => {
    if (state === ConnectionState.Connected && !agentParticipant) {
      setStatus('connecting', 'Connected. Waiting for the planning companion…');
    }
    if (state === ConnectionState.Disconnected) {
      agentParticipant = null;
      setStatus('offline');
    }
  });
  nextRoom.on(RoomEvent.TrackSubscribed, attachRemoteAudio);
  nextRoom.on(RoomEvent.TrackUnsubscribed, detachRemoteAudio);
  nextRoom.on(RoomEvent.ParticipantAttributesChanged, (_changed, participant) => agentStateChanged(participant));
  nextRoom.on(RoomEvent.ParticipantConnected, agentConnected);
  nextRoom.on(RoomEvent.ParticipantDisconnected, agentDisconnected);
  nextRoom.on(RoomEvent.Disconnected, () => {
    attachedAudio.forEach((element) => element.remove());
    attachedAudio = new Map();
    room = null;
    agentParticipant = null;
    processedAssistantSegments = new Set();
    connectButton.disabled = false;
    connectButton.querySelector('#orb-label').textContent = 'Start talking';
  });
  nextRoom.registerTextStreamHandler('lk.transcription', (reader, participant) => receiveTranscript(reader, participant));
}

async function createRoomCredentials() {
  return api('/api/token', { method: 'POST', body: JSON.stringify({}) });
}

async function startConversation() {
  if (room) {
    connectButton.disabled = true;
    await room.disconnect();
    try {
      await refreshReview();
      if (reviewProposals.length) {
        await showView('review');
        showToast(`${reviewProposals.length === 1 ? 'Your draft is' : 'Your drafts are'} ready to review.`);
      } else {
        showToast('Conversation ended. No draft was created — next time, say “make a draft” before ending.', 'note');
      }
    } catch (error) {
      showToast(error.message, 'error');
    } finally {
      connectButton.disabled = false;
    }
    return;
  }

  connectButton.disabled = true;
  setStatus('connecting');
  try {
    const { server_url: serverUrl, participant_token: participantToken } = await createRoomCredentials();
    const nextRoom = new Room({ adaptiveStream: true, dynacast: true });
    wireRoom(nextRoom);
    await nextRoom.connect(serverUrl, participantToken);
    room = nextRoom;
    nextRoom.remoteParticipants.forEach(agentConnected);
    await nextRoom.localParticipant.setMicrophoneEnabled(true);
    connectButton.querySelector('#orb-label').textContent = 'End conversation';
    connectButton.disabled = false;
  } catch (error) {
    console.error(error);
    setStatus('error', error.message || 'I could not start the voice conversation.');
    connectButton.disabled = false;
  }
}

function updateReviewSignals() {
  const count = reviewProposals.length;
  reviewCount.textContent = String(count);
  reviewCount.hidden = count === 0;
  draftHandoff.hidden = count === 0;
  if (count) {
    draftHandoffTitle.textContent = count === 1 ? 'A draft is ready' : `${count} drafts are ready`;
    draftHandoffCopy.textContent = 'Check the wording, timing, and steps before saving.';
  }
}

function localDateTimeValue(isoValue) {
  if (!isoValue) return '';
  const date = new Date(isoValue);
  if (Number.isNaN(date.getTime())) return '';
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function selectProposal(proposalId) {
  const proposal = reviewProposals.find((item) => item.id === proposalId);
  if (!proposal) return;
  selectedProposalId = proposal.id;
  draftList.querySelectorAll('.draft-list-item').forEach((item) => {
    const selected = item.dataset.proposalId === proposal.id;
    item.classList.toggle('is-selected', selected);
    item.setAttribute('aria-pressed', String(selected));
  });
  proposalKind.textContent = proposal.kind === 'idea' ? 'Idea' : 'Task';
  proposalTiming.textContent = proposal.timing_phrase || (proposal.due_date ? `Due ${proposal.due_date}` : 'No timing assumed');
  proposalTitle.value = proposal.title || '';
  proposalDescription.value = proposal.description || '';
  proposalDueDate.value = proposal.due_date || '';
  proposalWorkTime.value = localDateTimeValue(proposal.work_start_at);
  proposalSteps.value = (proposal.suggested_steps || []).join('\n');
  proposalSteps.disabled = proposal.kind === 'idea';
  proposalSteps.placeholder = proposal.kind === 'idea' ? 'Ideas do not need steps' : 'Add a simple first step';
  proposalSource.textContent = proposal.source_excerpt || 'No source excerpt was saved.';
  proposalMissing.textContent = proposal.missing_detail || '';
  proposalMissing.hidden = !proposal.missing_detail;
}

function renderReview() {
  updateReviewSignals();
  const hasDrafts = reviewProposals.length > 0;
  reviewEmpty.hidden = hasDrafts;
  reviewWorkspace.hidden = !hasDrafts;
  if (!hasDrafts) {
    selectedProposalId = null;
    return;
  }

  draftListCount.textContent = `${reviewProposals.length} ${reviewProposals.length === 1 ? 'draft' : 'drafts'}`;
  draftList.innerHTML = reviewProposals.map((proposal) => `
    <button class="draft-list-item" type="button" data-proposal-id="${proposal.id}" aria-pressed="false">
      <span class="draft-item-meta"><span>${escapeHtml(proposal.kind)}</span><span>${escapeHtml(proposal.due_date || proposal.timing_phrase || 'No date')}</span></span>
      <strong>${escapeHtml(proposal.title)}</strong>
      <small>${escapeHtml(proposal.description || proposal.source_excerpt || 'Ready for your review')}</small>
    </button>`).join('');
  draftList.querySelectorAll('.draft-list-item').forEach((item) => {
    item.addEventListener('click', () => selectProposal(item.dataset.proposalId));
  });
  const stillSelected = reviewProposals.some((proposal) => proposal.id === selectedProposalId);
  selectProposal(stillSelected ? selectedProposalId : reviewProposals[0].id);
}

async function refreshReview({ quiet = false } = {}) {
  try {
    const data = await api('/api/review');
    reviewProposals = data.proposals || [];
    renderReview();
  } catch (error) {
    if (!quiet) throw error;
    console.error('Could not refresh review drafts', error);
  }
}

reviewForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (!selectedProposalId) return;
  approveProposalButton.disabled = true;
  dismissProposalButton.disabled = true;
  try {
    const workTime = proposalWorkTime.value ? new Date(proposalWorkTime.value).toISOString() : null;
    await api(`/api/review/${selectedProposalId}/approve`, {
      method: 'POST',
      body: JSON.stringify({
        title: proposalTitle.value.trim(),
        description: proposalDescription.value.trim(),
        due_date: proposalDueDate.value || null,
        work_start_at: workTime,
        steps: proposalSteps.value.split('\n').map((step) => step.trim()).filter(Boolean),
      }),
    });
    await refreshReview();
    showToast('Approved and added to your board.');
    await showView('board');
  } catch (error) {
    showToast(error.message, 'error');
  } finally {
    approveProposalButton.disabled = false;
    dismissProposalButton.disabled = false;
  }
});

dismissProposalButton.addEventListener('click', async () => {
  if (!selectedProposalId) return;
  approveProposalButton.disabled = true;
  dismissProposalButton.disabled = true;
  try {
    await api(`/api/review/${selectedProposalId}/dismiss`, { method: 'POST', body: '{}' });
    await refreshReview();
    showToast('Draft dismissed.', 'note');
  } catch (error) {
    showToast(error.message, 'error');
  } finally {
    approveProposalButton.disabled = false;
    dismissProposalButton.disabled = false;
  }
});

function displayDate(value) {
  if (!value) return '';
  const date = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short', year: 'numeric' }).format(date);
}

function taskCard(task) {
  const timing = task.due_date
    ? `<span>Due ${escapeHtml(displayDate(task.due_date))}</span>`
    : task.work_start_at
      ? `<span>Work ${escapeHtml(displayDate(task.work_start_at))}</span>`
      : '<span>No date</span>';
  const steps = (task.steps || []).map((step) => `
    <label class="task-step">
      <input type="checkbox" data-step-id="${step.id}" ${step.completed ? 'checked' : ''} />
      <span>${escapeHtml(step.title)}</span>
    </label>`).join('');
  const statusActions = task.status === 'open'
    ? `<button type="button" data-task-id="${task.id}" data-next-status="completed">Mark complete</button>
       <button type="button" data-task-id="${task.id}" data-next-status="cancelled">Cancel</button>`
    : `<button type="button" data-task-id="${task.id}" data-next-status="open">Reopen</button>`;
  return `
    <article class="task-card" data-status="${task.status}">
      <div class="task-card-meta"><span class="kind-pill">${escapeHtml(task.kind)}</span>${timing}</div>
      <h3>${escapeHtml(task.title)}</h3>
      ${task.description ? `<p>${escapeHtml(task.description)}</p>` : ''}
      ${steps ? `<div class="task-steps">${steps}</div>` : ''}
      <div class="task-card-actions">${statusActions}</div>
    </article>`;
}

function renderBoard(tasks) {
  boardEmpty.hidden = tasks.length > 0;
  boardContent.hidden = tasks.length === 0;
  if (!tasks.length) {
    boardContent.innerHTML = '';
    return;
  }
  const groups = [
    { key: 'open', title: 'In progress', tasks: tasks.filter((task) => task.status === 'open' && task.kind === 'task') },
    { key: 'ideas', title: 'Ideas', tasks: tasks.filter((task) => task.status === 'open' && task.kind === 'idea') },
    { key: 'closed', title: 'Finished & set aside', tasks: tasks.filter((task) => task.status !== 'open') },
  ].filter((group) => group.tasks.length);
  boardContent.innerHTML = groups.map((group) => `
    <section class="board-column">
      <div class="section-label"><span>${group.title}</span><span>${group.tasks.length}</span></div>
      <div class="task-stack">${group.tasks.map(taskCard).join('')}</div>
    </section>`).join('');

  boardContent.querySelectorAll('[data-task-id]').forEach((button) => {
    button.addEventListener('click', async () => {
      button.disabled = true;
      try {
        await api(`/api/tasks/${button.dataset.taskId}/status`, {
          method: 'PATCH', body: JSON.stringify({ status: button.dataset.nextStatus }),
        });
        await refreshBoard();
      } catch (error) {
        showToast(error.message, 'error');
        button.disabled = false;
      }
    });
  });
  boardContent.querySelectorAll('[data-step-id]').forEach((checkbox) => {
    checkbox.addEventListener('change', async () => {
      checkbox.disabled = true;
      try {
        await api(`/api/steps/${checkbox.dataset.stepId}`, {
          method: 'PATCH', body: JSON.stringify({ completed: checkbox.checked }),
        });
      } catch (error) {
        checkbox.checked = !checkbox.checked;
        showToast(error.message, 'error');
      } finally {
        checkbox.disabled = false;
      }
    });
  });
}

async function refreshBoard() {
  const data = await api('/api/board');
  renderBoard(data.tasks || []);
}

connectButton.addEventListener('click', startConversation);

window.addEventListener('hashchange', () => showView(location.hash.slice(1), { updateHash: false }));
setStatus('offline');
showView(location.hash.slice(1) || 'talk', { updateHash: false });
refreshReview({ quiet: true });
