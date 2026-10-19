require('dotenv').config();
const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const crypto = require('crypto');
const admin = require('firebase-admin');
const TelegramBot = require('node-telegram-bot-api');
const rateLimit = require('express-rate-limit');

const app = express();
const PORT = process.env.PORT || 3000;

// --- CONFIGURATION ---
const BOT_TOKEN = process.env.TELEGRAM_BOT_TOKEN;
const CHANNEL_ID = process.env.TELEGRAM_CHANNEL_ID;
const FRONTEND_ORIGIN = process.env.FRONTEND_ORIGIN || '*'; // Vercel domain dalenge baad me
const FIREBASE_CREDENTIALS = JSON.parse(process.env.FIREBASE_SERVICE_ACCOUNT);

// --- SECURE PDF CATALOGUE ---
const PDF_CATALOGUE = [
  { id: 1, name: "Economics", url: "https://drive.google.com/file/d/1hbKSxeX6SWK0lpSWHo21vNK8l9F5IXJ9/view?usp=drivesdk" },
  { id: 2, name: "Physics", url: "https://drive.google.com/file/d/1PN9LaQCaWWCfV7xdNCb8PgC671Fs7hdQ/view?usp=drivesdk" },
  { id: 3, name: "Civics", url: "https://drive.google.com/file/d/1_t7x5irxluEdx7ugxo2lbdLctFss0dWD/view?usp=drivesdk" },
  { id: 4, name: "History", url: "https://drive.google.com/file/d/1AujJJqkmWFl9cFeB4_MsQ9ffU2m40vsB/view?usp=drivesdk" },
  { id: 5, name: "Maths", url: "https://drive.google.com/file/d/1bI5Siizo_vqftacfvZ_HR7vY3bDcgzMa/view?usp=drivesdk" },
  { id: 6, name: "Chemistry", url: "https://drive.google.com/file/d/1O890P8zKHkRk0jmaPp4cxGHvGn-lI8OY/view?usp=drivesdk" },
  { id: 7, name: "Biology", url: "https://drive.google.com/file/d/1oP8A7XC6-aPkZCwJLhAF_c2uNqXmdXzp/view?usp=drivesdk" },
  { id: 8, name: "Sanskrit", url: "https://drive.google.com/file/d/1X0CZR2AZ33EuEHAhFtzi9wYpsBts6FjB/view?usp=drivesdk" },
  { id: 9, name: "English", url: "https://drive.google.com/file/d/1GSTyzCiPRwcmfGiaFR-NJRBe2El5UVEj/view?usp=drivesdk" }
];

// --- FIREBASE SETUP ---
admin.initializeApp({
  credential: admin.credential.cert(FIREBASE_CREDENTIALS),
  databaseURL: process.env.FIREBASE_DATABASE_URL
});
const db = admin.database();

// --- TELEGRAM BOT ---
const bot = new TelegramBot(BOT_TOKEN, { polling: true });

// --- MIDDLEWARE ---
app.use(helmet());
app.use(express.json());
// CORS updated for Token based Auth
app.use(cors({ origin: FRONTEND_ORIGIN, methods: "GET,POST,PUT,DELETE", allowedHeaders: "Content-Type,Authorization" }));

const limiter = rateLimit({ windowMs: 15 * 60 * 1000, max: 100 });
app.use('/api/', limiter);

// --- AUTH MIDDLEWARE (Bearer Token) ---
async function requireAuth(req, res, next) {
  const authHeader = req.headers.authorization;
  if (!authHeader || !authHeader.startsWith('Bearer ')) return res.status(401).json({ error: 'Unauthorized' });

  const sessionToken = authHeader.split(' ')[1];
  const sessionRef = db.ref(`sessions/${sessionToken}`);
  const snap = await sessionRef.once('value');
  
  if (!snap.exists() || snap.val().expiresAt < Date.now()) {
    return res.status(401).json({ error: 'Session expired' });
  }
  
  req.userId = snap.val().telegramId;
  next();
}

// --- API ENDPOINTS ---

// 1. Generate one-time binding ticket
app.get('/api/auth/ticket', async (req, res) => {
  const ticket = crypto.randomBytes(16).toString('hex');
  await db.ref(`bindTickets/${ticket}`).set({
    status: 'pending',
    expiresAt: Date.now() + 10 * 60 * 1000 // 10 minutes
  });
  res.json({ ticket });
});

// 2. Poll for binding status
app.get('/api/auth/status/:ticket', async (req, res) => {
  const { ticket } = req.params;
  const snap = await db.ref(`bindTickets/${ticket}`).once('value');
  
  if (!snap.exists()) return res.status(404).json({ error: 'Invalid ticket' });
  
  const data = snap.val();
  if (data.status === 'completed') {
    const sessionToken = crypto.randomBytes(32).toString('hex');
    await db.ref(`sessions/${sessionToken}`).set({
      telegramId: data.telegramId,
      expiresAt: Date.now() + 7 * 24 * 60 * 60 * 1000 // 7 days
    });
    
    await db.ref(`bindTickets/${ticket}`).remove(); // Cleanup
    return res.json({ success: true, sessionToken });
  }
  res.json({ status: 'pending' });
});

// 3. Get User Profile
app.get('/api/user', requireAuth, async (req, res) => {
  const snap = await db.ref(`users/${req.userId}`).once('value');
  if (!snap.exists()) return res.status(404).json({ error: 'User not found' });
  res.json(snap.val());
});

// 4. Get Unlocked PDFs
app.get('/api/pdfs', requireAuth, async (req, res) => {
  const snap = await db.ref(`users/${req.userId}`).once('value');
  const user = snap.val();
  const referrals = user.verifiedReferrals || 0;
  
  // UNLOCK POLICY
  let unlockedCount = referrals;
  if (referrals === 8 || referrals === 9) unlockedCount = 8;
  if (referrals >= 10) unlockedCount = 9;

  const results = PDF_CATALOGUE.map((pdf, index) => ({
    id: pdf.id,
    name: pdf.name,
    unlocked: index < unlockedCount,
    url: index < unlockedCount ? pdf.url : null
  }));
  
  res.json({ referrals, unlockedCount, subjects: results });
});

// --- TELEGRAM BOT LOGIC ---
bot.onText(/\/start (.+)/, async (msg, match) => {
  const chatId = msg.chat.id;
  const ticket = match[1];
  
  const snap = await db.ref(`bindTickets/${ticket}`).once('value');
  if (!snap.exists() || snap.val().status !== 'pending' || snap.val().expiresAt < Date.now()) {
    return bot.sendMessage(chatId, "❌ Invalid or expired ticket. Go to the website and try again.");
  }

  const telegramId = msg.from.id;
  const userRef = db.ref(`users/${telegramId}`);
  const userSnap = await userRef.once('value');
  
  let inviteLink = userSnap.exists() ? userSnap.val().inviteLink : null;
  
  if (!inviteLink) {
    try {
      const linkReq = await bot.createChatInviteLink(CHANNEL_ID, {
        name: `Ref: ${msg.from.first_name}`,
        creates_join_request: false
      });
      inviteLink = linkReq.invite_link;
      const linkHash = inviteLink.split('/').pop();
      await db.ref(`referralInvites/${linkHash}`).set(telegramId);
    } catch (e) {
      return bot.sendMessage(chatId, "⚠️ Failed to generate link. Make sure I am Admin.");
    }
  }

  await userRef.update({
    telegramId,
    firstName: msg.from.first_name,
    lastName: msg.from.last_name || '',
    username: msg.from.username || '',
    inviteLink,
    verifiedReferrals: userSnap.exists() ? userSnap.val().verifiedReferrals : 0
  });

  await db.ref(`bindTickets/${ticket}`).update({ status: 'completed', telegramId });
  bot.sendMessage(chatId, "✅ Account Bound! Return to the website browser.");
});

bot.on('chat_member', async (msg) => {
  if (msg.chat.id.toString() !== CHANNEL_ID) return;
  
  const newMember = msg.new_chat_member;
  const inviteLink = msg.invite_link;
  
  if (newMember.status === 'member' && inviteLink) {
    const linkHash = inviteLink.invite_link.split('/').pop();
    const joinedId = newMember.user.id;
    
    const linkSnap = await db.ref(`referralInvites/${linkHash}`).once('value');
    if (!linkSnap.exists()) return;
    const referrerId = linkSnap.val();
    
    if (referrerId === joinedId) return; // Anti-self-referral

    const countedRef = db.ref(`countedJoins/${joinedId}`);
    const alreadyCounted = await countedRef.once('value');
    
    if (!alreadyCounted.exists()) {
      await countedRef.set({ referrerId, timestamp: Date.now() });
      const referrerRef = db.ref(`users/${referrerId}/verifiedReferrals`);
      await referrerRef.transaction(current => (current || 0) + 1);
    }
  }
});

app.listen(PORT, () => console.log(`Backend running on port ${PORT}`));
