/**
 * RECON HFT — Mobile App
 * Auth: email+password on web (Google OAuth blocked in iframe),
 *       Google OAuth on native iOS/Android.
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Linking,
  Platform,
  Modal,
  TextInput,
  Dimensions,
  KeyboardAvoidingView,
  ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons, MaterialCommunityIcons } from '@expo/vector-icons';
import Animated, {
  FadeIn,
  FadeInDown,
  FadeInUp,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withSequence,
  withTiming,
  interpolate,
} from 'react-native-reanimated';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

import { useAuth } from '@/hooks/useAuth';
import { blink } from '@/lib/blink';
import { colors, spacing, typography, borderRadius } from '@/constants/design';

const { width: W } = Dimensions.get('window');

// ─── Types ────────────────────────────────────────────────────────────────────
interface Market {
  id: string;
  title: string;
  currentPrice: number;
  edge: number;
  expiresAt: string;
}
interface Wallet {
  id: string;
  walletAddress: string;
  walletType: 'custodial' | 'browser';
}
type TabId = 'DASHBOARD' | 'STRATEGY' | 'WALLETS' | 'LOGS';

// ─── Pulse dot ────────────────────────────────────────────────────────────────
function PulseDot({ color = colors.primary }: { color?: string }) {
  const scale = useSharedValue(1);
  useEffect(() => {
    scale.value = withRepeat(
      withSequence(withTiming(1.7, { duration: 800 }), withTiming(1, { duration: 800 })),
      -1, true
    );
  }, []);
  const style = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }],
    opacity: interpolate(scale.value, [1, 1.7], [1, 0.2]),
  }));
  return (
    <View style={{ width: 10, height: 10, alignItems: 'center', justifyContent: 'center' }}>
      <Animated.View style={[{ width: 10, height: 10, borderRadius: 5, backgroundColor: color }, style]} />
    </View>
  );
}

// ─── Metric tile ──────────────────────────────────────────────────────────────
function Tile({ label, value, sub, accent }: { label: string; value: string; sub?: string; accent?: boolean }) {
  return (
    <View style={[ts.tile, accent && ts.accent]}>
      {accent && <LinearGradient colors={['rgba(204,255,0,0.15)', 'transparent']} style={StyleSheet.absoluteFillObject} />}
      <Text style={ts.label}>{label}</Text>
      <Text style={[ts.value, accent && { color: colors.primary }]}>{value}</Text>
      {sub && <Text style={ts.sub}>{sub}</Text>}
    </View>
  );
}
const ts = StyleSheet.create({
  tile: { flex: 1, backgroundColor: '#111', borderRadius: 14, padding: 14, gap: 3 },
  accent: { borderWidth: 1, borderColor: 'rgba(204,255,0,0.2)', overflow: 'hidden' },
  label: { fontSize: 9, fontWeight: '700', color: '#555', letterSpacing: 1.5, textTransform: 'uppercase' },
  value: { fontSize: 20, fontWeight: '800', color: '#fff' },
  sub: { fontSize: 10, fontWeight: '600', color: colors.success },
});

// ─── Market row ───────────────────────────────────────────────────────────────
function MarketRow({ market, delay = 0 }: { market: Market; delay?: number }) {
  const isUp = market.title.toLowerCase().includes('above');
  return (
    <Animated.View entering={FadeInDown.delay(delay).springify()}>
      <TouchableOpacity style={mr.row} activeOpacity={0.75}>
        <View style={[mr.dir, { backgroundColor: isUp ? 'rgba(0,255,0,0.1)' : 'rgba(255,50,50,0.1)' }]}>
          <Ionicons name={isUp ? 'arrow-up' : 'arrow-down'} size={13} color={isUp ? colors.success : colors.error} />
        </View>
        <View style={mr.info}>
          <Text style={mr.title} numberOfLines={1}>{market.title}</Text>
          <Text style={mr.exp}>EXP {new Date(market.expiresAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</Text>
        </View>
        <View style={mr.right}>
          <Text style={mr.price}>${Number(market.currentPrice).toFixed(2)}</Text>
          <View style={mr.pill}><Text style={mr.pillText}>+{market.edge}%</Text></View>
        </View>
      </TouchableOpacity>
    </Animated.View>
  );
}
const mr = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#111', borderRadius: 14, padding: 14, gap: 12, borderLeftWidth: 3, borderLeftColor: colors.primary },
  dir: { width: 30, height: 30, borderRadius: 9, alignItems: 'center', justifyContent: 'center' },
  info: { flex: 1 },
  title: { fontSize: 13, fontWeight: '700', color: '#fff' },
  exp: { fontSize: 10, color: '#555', marginTop: 2 },
  right: { alignItems: 'flex-end', gap: 4 },
  price: { fontSize: 15, fontWeight: '800', color: '#fff' },
  pill: { backgroundColor: 'rgba(204,255,0,0.12)', borderRadius: 5, paddingHorizontal: 5, paddingVertical: 2 },
  pillText: { fontSize: 9, fontWeight: '900', color: colors.primary },
});

// ─── Bottom nav ───────────────────────────────────────────────────────────────
const TABS: { id: TabId; icon: string }[] = [
  { id: 'DASHBOARD', icon: 'pulse-outline' },
  { id: 'STRATEGY',  icon: 'analytics-outline' },
  { id: 'WALLETS',   icon: 'wallet-outline' },
  { id: 'LOGS',      icon: 'terminal-outline' },
];
function BottomNav({ active, onPress }: { active: TabId; onPress: (id: TabId) => void }) {
  return (
    <View style={bn.bar}>
      {TABS.map(t => {
        const on = active === t.id;
        return (
          <TouchableOpacity key={t.id} style={bn.item} onPress={() => onPress(t.id)}>
            <Ionicons name={t.icon as any} size={22} color={on ? colors.primary : '#444'} />
            <Text style={[bn.label, on && { color: colors.primary }]}>{t.id}</Text>
            {on && <View style={bn.dot} />}
          </TouchableOpacity>
        );
      })}
    </View>
  );
}
const bn = StyleSheet.create({
  bar: { position: 'absolute', bottom: 0, left: 0, right: 0, flexDirection: 'row', backgroundColor: '#080808', borderTopWidth: 1, borderTopColor: '#1a1a1a', paddingTop: 10, paddingBottom: Platform.OS === 'ios' ? 28 : 12 },
  item: { flex: 1, alignItems: 'center', gap: 3 },
  label: { fontSize: 8, fontWeight: '700', color: '#444', letterSpacing: 1 },
  dot: { width: 4, height: 4, borderRadius: 2, backgroundColor: colors.primary },
});

// ─────────────────────────────────────────────────────────────────────────────
//  ONBOARDING — 3 info steps + auth (email on web, Google on native)
// ─────────────────────────────────────────────────────────────────────────────
const STEPS = [
  { icon: 'flash-circle',  title: 'RECON HFT',           body: 'Bayesian edge detection for\n5-minute BTC prediction markets.' },
  { icon: 'trending-up',   title: 'PRECISION\nEXECUTION', body: 'Z-Score limit orders placed at\nthe optimal probability price.' },
  { icon: 'shield-check',  title: 'RISK\nCONTROLLED',    body: 'Stop-loss, take-profit, Kelly\nsizing & drawdown protection.' },
];

function OnboardingScreen({
  isWeb,
  authError,
  onGoogle,
  onEmail,
  onSignUp,
}: {
  isWeb: boolean;
  authError: string | null;
  onGoogle: () => Promise<void>;
  onEmail: (e: string, p: string) => Promise<void>;
  onSignUp: (e: string, p: string) => Promise<void>;
}) {
  const [step, setStep] = useState(0);
  const [authStep, setAuthStep] = useState<'info' | 'signin' | 'signup'>('info');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [localError, setLocalError] = useState('');

  const isLast = step === STEPS.length - 1;

  const handleEmailAuth = useCallback(async (isSignUp: boolean) => {
    if (!email.trim() || !password) {
      setLocalError('Email and password are required.');
      return;
    }
    setBusy(true);
    setLocalError('');
    try {
      if (isSignUp) await onSignUp(email.trim(), password);
      else await onEmail(email.trim(), password);
    } catch (e: any) {
      setLocalError(e?.message || 'Authentication failed. Please try again.');
    } finally {
      setBusy(false);
    }
  }, [email, password, onEmail, onSignUp]);

  const handleGoogle = useCallback(async () => {
    setBusy(true);
    setLocalError('');
    try { await onGoogle(); }
    catch (e: any) { setLocalError(e?.message || 'Google sign-in failed.'); }
    finally { setBusy(false); }
  }, [onGoogle]);

  // ── Auth form (last step on web) ───────────────────────────────────────────
  if (authStep !== 'info') {
    const isSignUp = authStep === 'signup';
    const busy = busy; // This was a typo in the original code, should be `busy`
    const errorMsg = authError || localError;

    return (
      <View style={ob.container}>
        <LinearGradient colors={['rgba(204,255,0,0.08)', '#000']} style={StyleSheet.absoluteFillObject} />
        <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={ob.form}>
          <TouchableOpacity style={ob.backRow} onPress={() => setAuthStep('info')}>
            <Ionicons name="arrow-back" size={16} color="#555" />
            <Text style={ob.backText}>Back</Text>
          </TouchableOpacity>

          <Animated.View entering={FadeInDown}>
            <Text style={ob.formTitle}>{isSignUp ? 'CREATE_ACCOUNT' : 'SIGN_IN'}</Text>
            <Text style={ob.formSub}>RECON HFT TERMINAL v2</Text>

            {isWeb && (
              <View style={[ob.errorBox, { backgroundColor: 'rgba(255,165,0,0.1)', borderColor: 'rgba(255,165,0,0.3)' }]}>
                <Ionicons name="information-circle-outline" size={14} color="#FFA500" />
                <Text style={[ob.errorText, { color: '#FFA500' }]}>
                  Web Preview restricted: Google Login is unavailable in this environment. Please use Email + Password.
                </Text>
              </View>
            )}

            {!!errorMsg && (
              <View style={ob.errorBox}>
                <Ionicons name="alert-circle-outline" size={14} color={colors.error} />
                <Text style={ob.errorText}>{errorMsg}</Text>
              </View>
            )}

            <TextInput
              style={ob.input}
              placeholder="Email address"
              placeholderTextColor="#444"
              value={email}
              onChangeText={setEmail}
              autoCapitalize="none"
              keyboardType="email-address"
              autoCorrect={false}
            />
            <TextInput
              style={ob.input}
              placeholder="Password"
              placeholderTextColor="#444"
              value={password}
              onChangeText={setPassword}
              secureTextEntry
            />

            <TouchableOpacity
              style={[ob.btn, busy && { opacity: 0.6 }]}
              onPress={() => handleEmailAuth(isSignUp)}
              disabled={busy}
            >
              {busy
                ? <ActivityIndicator color="#000" />
                : <Text style={ob.btnText}>{isSignUp ? 'CREATE ACCOUNT' : 'SIGN IN'}</Text>
              }
            </TouchableOpacity>

            <TouchableOpacity onPress={() => { setAuthStep(isSignUp ? 'signin' : 'signup'); setLocalError(''); }}>
              <Text style={ob.switchText}>
                {isSignUp ? 'Already have an account? Sign in' : "Don't have an account? Create one"}
              </Text>
            </TouchableOpacity>

            {/* Google — native only */}
            {!isWeb && (
              <TouchableOpacity style={[ob.googleBtn, busy && { opacity: 0.6 }]} onPress={handleGoogle} disabled={busy}>
                <Ionicons name="logo-google" size={18} color="#fff" />
                <Text style={ob.googleText}>Continue with Google</Text>
              </TouchableOpacity>
            )}

            <Text style={ob.disclaimer}>
              Trading prediction markets carries significant financial risk.
            </Text>
          </Animated.View>
        </KeyboardAvoidingView>
      </View>
    );
  }

  // ── Info steps ─────────────────────────────────────────────────────────────
  const cur = STEPS[step];
  return (
    <View style={ob.container}>
      <LinearGradient colors={['rgba(204,255,0,0.08)', '#000']} style={StyleSheet.absoluteFillObject} />

      {!isLast && (
        <TouchableOpacity style={ob.skip} onPress={() => setStep(STEPS.length - 1)}>
          <Text style={ob.skipText}>Skip →</Text>
        </TouchableOpacity>
      )}

      <Animated.View key={step} entering={FadeInUp.duration(350)} style={ob.content}>
        <MaterialCommunityIcons name={cur.icon as any} size={88} color={colors.primary} />
        <Text style={ob.title}>{cur.title}</Text>
        <Text style={ob.body}>{cur.body}</Text>
      </Animated.View>

      <View style={ob.dotsRow}>
        {STEPS.map((_, i) => (
          <View key={i} style={[ob.dotBase, i === step && ob.dotActive]} />
        ))}
      </View>

      <Animated.View entering={FadeInDown.delay(250)} style={ob.actions}>
        {!isLast ? (
          <TouchableOpacity style={ob.btn} onPress={() => setStep(s => s + 1)}>
            <Text style={ob.btnText}>NEXT →</Text>
          </TouchableOpacity>
        ) : (
          <>
            <TouchableOpacity style={ob.btn} onPress={() => setAuthStep('signin')}>
              <Text style={ob.btnText}>SIGN IN</Text>
            </TouchableOpacity>
            <TouchableOpacity style={ob.outlineBtn} onPress={() => setAuthStep('signup')}>
              <Text style={ob.outlineBtnText}>CREATE ACCOUNT</Text>
            </TouchableOpacity>
            {!isWeb && (
              <TouchableOpacity style={ob.googleBtn} onPress={handleGoogle} disabled={busy}>
                <Ionicons name="logo-google" size={18} color="#000" />
                <Text style={[ob.googleText, { color: '#000' }]}>Continue with Google</Text>
              </TouchableOpacity>
            )}
            <Text style={ob.disclaimer}>
              By continuing you agree to the risk disclaimer. HFT trading can result in losses.
            </Text>
          </>
        )}
      </Animated.View>
    </View>
  );
}

const ob = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#000', paddingHorizontal: 28, paddingTop: 72, paddingBottom: 48, justifyContent: 'space-between' },
  skip: { position: 'absolute', top: 56, right: 28 },
  skipText: { fontSize: 13, color: '#555', fontWeight: '700' },
  content: { flex: 1, alignItems: 'flex-start', justifyContent: 'center', gap: 18 },
  title: { fontSize: 46, fontWeight: '900', color: colors.primary, lineHeight: 50, letterSpacing: -1 },
  body: { fontSize: 16, color: '#888', lineHeight: 24, maxWidth: W * 0.78 },
  dotsRow: { flexDirection: 'row', gap: 8, marginBottom: 28 },
  dotBase: { width: 6, height: 6, borderRadius: 3, backgroundColor: '#222' },
  dotActive: { backgroundColor: colors.primary, width: 22 },
  actions: { gap: 14 },
  btn: { backgroundColor: colors.primary, height: 56, alignItems: 'center', justifyContent: 'center', borderRadius: 0 },
  btnText: { fontSize: 14, fontWeight: '900', color: '#000', letterSpacing: 1.5 },
  outlineBtn: { height: 56, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: colors.primary },
  outlineBtnText: { fontSize: 14, fontWeight: '900', color: colors.primary, letterSpacing: 1.5 },
  googleBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10, height: 52, backgroundColor: colors.primary, borderRadius: 0 },
  googleText: { fontSize: 14, fontWeight: '800', color: '#000' },
  disclaimer: { fontSize: 11, color: '#444', textAlign: 'center', lineHeight: 16 },
  // form
  form: { flex: 1, justifyContent: 'center', gap: 16, paddingTop: 60 },
  backRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 },
  backText: { fontSize: 13, color: '#555', fontWeight: '600' },
  formTitle: { fontSize: 28, fontWeight: '900', color: colors.primary, letterSpacing: 2 },
  formSub: { fontSize: 14, color: '#666', marginTop: -8, marginBottom: 4 },
  errorBox: { flexDirection: 'row', alignItems: 'flex-start', gap: 8, backgroundColor: 'rgba(255,0,0,0.08)', borderRadius: 10, padding: 12, borderWidth: 1, borderColor: 'rgba(255,0,0,0.2)' },
  errorText: { flex: 1, fontSize: 12, color: colors.error, lineHeight: 18 },
  input: { backgroundColor: '#111', borderRadius: 0, height: 52, paddingHorizontal: 16, color: '#fff', fontSize: 14, borderBottomWidth: 1, borderBottomColor: '#333' },
  switchText: { textAlign: 'center', fontSize: 13, color: '#666', textDecorationLine: 'underline' },
});

// ─────────────────────────────────────────────────────────────────────────────
//  DASHBOARD TAB
// ─────────────────────────────────────────────────────────────────────────────
function DashboardTab({ markets }: { markets: Market[] }) {
  return (
    <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ gap: 18, paddingBottom: 16 }}>
      <Animated.View entering={FadeIn.duration(500)} style={dash.ringWrap}>
        <LinearGradient colors={[colors.primary, '#88FF00']} style={dash.ring}>
          <View style={dash.ringInner}>
            <Text style={dash.ringLabel}>SESSION P&L</Text>
            <Text style={dash.ringValue}>+$1,420</Text>
            <Text style={dash.ringSub}>+14.2% today</Text>
          </View>
        </LinearGradient>
      </Animated.View>

      <Animated.View entering={FadeInDown.delay(80)} style={{ flexDirection: 'row', gap: 10 }}>
        <Tile label="Balance" value="$5,240" sub="+4.2%" accent />
        <Tile label="Trades" value="312" sub="+12/hr" />
        <Tile label="Win Rate" value="68%" sub="avg 9.4% edge" />
      </Animated.View>

      <Animated.View entering={FadeInDown.delay(130)} style={dash.pill}>
        <PulseDot />
        <Text style={dash.pillText}>BAYESIAN_V2_Z_SCORE — RUNNING</Text>
      </Animated.View>

      {/* Horizontal edge cards */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginHorizontal: -20 }} contentContainerStyle={{ paddingHorizontal: 20, gap: 12 }}>
        {markets.map(m => (
          <View key={m.id} style={dash.card}>
            <Text style={dash.cardTitle} numberOfLines={1}>{m.title}</Text>
            <View style={dash.edgeBar}>
              <View style={[dash.edgeFill, { width: `${Math.min(100, m.edge * 5)}%` as any }]} />
            </View>
            <Text style={dash.cardEdge}>{m.edge}% EDGE</Text>
          </View>
        ))}
      </ScrollView>

      <Text style={dash.sectionLabel}>MARKET_PULSE</Text>
      <View style={{ gap: 10 }}>
        {markets.map((m, i) => <MarketRow key={m.id} market={m} delay={i * 55} />)}
      </View>
    </ScrollView>
  );
}
const dash = StyleSheet.create({
  ringWrap: { alignItems: 'center' },
  ring: { width: 176, height: 176, borderRadius: 88, padding: 11, alignItems: 'center', justifyContent: 'center' },
  ringInner: { width: 154, height: 154, borderRadius: 77, backgroundColor: '#000', alignItems: 'center', justifyContent: 'center', gap: 3 },
  ringLabel: { fontSize: 9, fontWeight: '700', color: '#555', letterSpacing: 1.5 },
  ringValue: { fontSize: 32, fontWeight: '900', color: colors.primary, letterSpacing: -1 },
  ringSub: { fontSize: 11, fontWeight: '700', color: colors.success },
  pill: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: 'rgba(204,255,0,0.06)', borderRadius: 10, paddingHorizontal: 14, paddingVertical: 10, borderWidth: 1, borderColor: 'rgba(204,255,0,0.12)' },
  pillText: { fontSize: 10, fontWeight: '800', color: colors.primary, letterSpacing: 1 },
  card: { width: 166, backgroundColor: '#111', borderRadius: 14, padding: 14, gap: 10 },
  cardTitle: { fontSize: 12, fontWeight: '700', color: '#fff' },
  edgeBar: { height: 4, backgroundColor: '#1a1a1a', borderRadius: 2 },
  edgeFill: { height: '100%', backgroundColor: colors.primary, borderRadius: 2 },
  cardEdge: { fontSize: 9, fontWeight: '900', color: colors.primary },
  sectionLabel: { fontSize: 10, fontWeight: '800', color: colors.primary, letterSpacing: 2 },
});

// ─────────────────────────────────────────────────────────────────────────────
//  STRATEGY TAB
// ─────────────────────────────────────────────────────────────────────────────
const PARAMS = [
  { k: 'STRATEGY_ID',     v: 'BAYESIAN_V2_Z_SCORE' },
  { k: 'MIN_EDGE',        v: '10.0%' },
  { k: 'VOL_PROXY (σ)',   v: '100 USD / 5min' },
  { k: 'KELLY_FRACTION',  v: '0.25' },
  { k: 'HEDGE_MODE',      v: 'DELTA_NEUTRAL' },
  { k: 'ORDER_TYPE',      v: 'LIMIT_ONLY' },
  { k: 'MAX_DRAWDOWN',    v: '15%' },
  { k: 'STOP_LOSS',       v: '5% prob shift' },
  { k: 'TAKE_PROFIT',     v: '15% prob shift' },
  { k: 'TIME_DECAY',      v: 'SQRT(t/T)' },
];

function StrategyTab({ markets }: { markets: Market[] }) {
  return (
    <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ gap: 20, paddingBottom: 16 }}>
      <Text style={st.sectionLabel}>EXECUTION_PARAMS</Text>
      <View style={st.table}>
        {PARAMS.map((p, i) => (
          <View key={p.k} style={[st.row, i < PARAMS.length - 1 && st.rowBorder]}>
            <Text style={st.key}>{p.k}</Text>
            <Text style={st.val}>{p.v}</Text>
          </View>
        ))}
      </View>

      <Text style={st.sectionLabel}>SIGNAL_MATRIX</Text>
      <View style={{ gap: 10 }}>
        {markets.map(m => {
          const strong = m.edge >= 10;
          return (
            <View key={m.id} style={st.signalRow}>
              <View style={[st.dot, { backgroundColor: strong ? colors.primary : '#2a2a2a' }]} />
              <Text style={st.signalTitle} numberOfLines={1}>{m.title}</Text>
              <Text style={[st.badge, { color: strong ? colors.primary : '#444' }]}>
                {strong ? 'STRONG_BUY' : 'NEUTRAL'}
              </Text>
            </View>
          );
        })}
      </View>

      <View style={st.infoBox}>
        <Text style={st.infoHead}>FORMULA</Text>
        <Text style={st.infoText}>
          {'Z = (BTC − Strike) / (σ × √(t/T))\n\nP(Yes) ≈ 0.5 + Z/2\n\nEdge = P(Yes) − Market_Price\nEnter when Edge > threshold'}
        </Text>
      </View>
    </ScrollView>
  );
}
const st = StyleSheet.create({
  sectionLabel: { fontSize: 10, fontWeight: '800', color: colors.primary, letterSpacing: 2 },
  table: { backgroundColor: '#111', borderRadius: 14, overflow: 'hidden' },
  row: { flexDirection: 'row', justifyContent: 'space-between', padding: 13, alignItems: 'center' },
  rowBorder: { borderBottomWidth: 1, borderBottomColor: '#1a1a1a' },
  key: { fontSize: 11, fontWeight: '700', color: '#555' },
  val: { fontSize: 11, fontWeight: '800', color: colors.primary },
  signalRow: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#111', borderRadius: 12, padding: 14, gap: 12 },
  dot: { width: 8, height: 8, borderRadius: 4 },
  signalTitle: { flex: 1, fontSize: 13, fontWeight: '700', color: '#fff' },
  badge: { fontSize: 9, fontWeight: '900', letterSpacing: 0.5 },
  infoBox: { backgroundColor: '#0d0d0d', borderRadius: 14, padding: 18, borderWidth: 1, borderColor: '#1a1a1a' },
  infoHead: { fontSize: 9, fontWeight: '800', color: '#555', letterSpacing: 2, marginBottom: 10 },
  infoText: { fontSize: 13, color: '#666', lineHeight: 22, fontFamily: Platform.OS === 'ios' ? 'Courier' : 'monospace' },
});

// ─────────────────────────────────────────────────────────────────────────────
//  WALLETS TAB
// ─────────────────────────────────────────────────────────────────────────────
function WalletsTab({ user }: { user: any }) {
  const qc = useQueryClient();
  const [showModal, setShowModal] = useState(false);
  const [addr, setAddr] = useState('');
  const [type, setType] = useState<'custodial' | 'browser'>('custodial');
  const [focused, setFocused] = useState(false);

  const { data: wallets = [], isLoading } = useQuery<Wallet[]>({
    queryKey: ['wallets', user?.id],
    queryFn: async () => {
      if (!user) return [];
      return (await blink.db.table('user_wallets').list({ where: { user_id: user.id } })) as Wallet[];
    },
    enabled: !!user,
  });

  const addMut = useMutation({
    mutationFn: async () => {
      if (!user || !addr.trim()) throw new Error('Wallet address is required');
      return blink.db.table('user_wallets').create({ userId: user.id, walletAddress: addr.trim(), walletType: type });
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['wallets', user?.id] }); setShowModal(false); setAddr(''); },
  });

  const removeMut = useMutation({
    mutationFn: (id: string) => blink.db.table('user_wallets').delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['wallets', user?.id] }),
  });

  return (
    <View style={{ flex: 1 }}>
      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ gap: 14, paddingBottom: 16 }}>
        <View style={wl.header}>
          <Text style={wl.sectionLabel}>LINKED_WALLETS</Text>
          <TouchableOpacity style={wl.addBtn} onPress={() => setShowModal(true)}>
            <Ionicons name="add" size={16} color="#000" />
            <Text style={wl.addText}>LINK</Text>
          </TouchableOpacity>
        </View>

        {isLoading
          ? <ActivityIndicator color={colors.primary} style={{ paddingTop: 40 }} />
          : wallets.length === 0
            ? (
              <Animated.View entering={FadeIn} style={wl.empty}>
                <MaterialCommunityIcons name="wallet-outline" size={44} color="#1a1a1a" />
                <Text style={wl.emptyText}>No wallets linked yet.{'\n'}Connect one to start trading.</Text>
                <TouchableOpacity style={wl.emptyBtn} onPress={() => setShowModal(true)}>
                  <Text style={wl.emptyBtnText}>+ CONNECT WALLET</Text>
                </TouchableOpacity>
              </Animated.View>
            ) : (
              <View style={{ gap: 10 }}>
                {wallets.map(w => (
                  <View key={w.id} style={wl.row}>
                    <Ionicons name={w.walletType === 'custodial' ? 'wallet-outline' : 'globe-outline'} size={17} color={colors.primary} />
                    <Text style={wl.addr} numberOfLines={1}>{w.walletAddress}</Text>
                    <Text style={wl.tag}>{w.walletType}</Text>
                    <TouchableOpacity onPress={() => removeMut.mutate(w.id)}>
                      <Ionicons name="close-circle" size={17} color="#333" />
                    </TouchableOpacity>
                  </View>
                ))}
              </View>
            )
        }

        <View style={{ flexDirection: 'row', gap: 12, marginTop: 6 }}>
          {([
            { icon: 'bank-outline', title: 'Custodial', body: 'Polymarket-managed. No seed phrase.' },
            { icon: 'earth',        title: 'Browser',   body: 'MetaMask / Rabby. Self-custodied.' },
          ] as const).map(c => (
            <View key={c.title} style={wl.infoCard}>
              <MaterialCommunityIcons name={c.icon as any} size={22} color={colors.primary} />
              <Text style={wl.infoTitle}>{c.title}</Text>
              <Text style={wl.infoBody}>{c.body}</Text>
            </View>
          ))}
        </View>
      </ScrollView>

      <Modal visible={showModal} animationType="slide" transparent>
        <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
          <View style={wl.modalBg}>
            <Animated.View entering={FadeInDown.springify()} style={wl.sheet}>
              <View style={wl.handle} />
              <Text style={wl.sheetTitle}>CONNECT WALLET</Text>

              <View style={wl.typeTabs}>
                {(['custodial', 'browser'] as const).map(t => (
                  <TouchableOpacity key={t} style={[wl.typeTab, type === t && wl.typeTabOn]} onPress={() => setType(t)}>
                    <Ionicons name={t === 'custodial' ? 'wallet-outline' : 'globe-outline'} size={15} color={type === t ? '#000' : '#555'} />
                    <Text style={[wl.typeText, type === t && { color: '#000' }]}>{t.toUpperCase()}</Text>
                  </TouchableOpacity>
                ))}
              </View>

              <View style={[wl.inputWrap, focused && wl.inputFocused]}>
                <Ionicons name="link-outline" size={17} color={focused ? colors.primary : '#444'} />
                <TextInput
                  style={wl.input}
                  placeholder="0x… or Polymarket address"
                  placeholderTextColor="#444"
                  value={addr}
                  onChangeText={setAddr}
                  onFocus={() => setFocused(true)}
                  onBlur={() => setFocused(false)}
                  autoCapitalize="none"
                  autoCorrect={false}
                />
              </View>

              <TouchableOpacity
                style={[wl.confirmBtn, (!addr.trim() || addMut.isPending) && { opacity: 0.5 }]}
                onPress={() => addMut.mutate()}
                disabled={!addr.trim() || addMut.isPending}
              >
                {addMut.isPending
                  ? <ActivityIndicator color="#000" />
                  : <Text style={wl.confirmText}>CONFIRM CONNECT</Text>
                }
              </TouchableOpacity>

              <TouchableOpacity onPress={() => { setShowModal(false); setAddr(''); }} style={{ alignItems: 'center', paddingVertical: 10 }}>
                <Text style={{ fontSize: 13, color: '#555' }}>Cancel</Text>
              </TouchableOpacity>
            </Animated.View>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </View>
  );
}
const wl = StyleSheet.create({
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  sectionLabel: { fontSize: 10, fontWeight: '800', color: colors.primary, letterSpacing: 2 },
  addBtn: { flexDirection: 'row', alignItems: 'center', gap: 5, backgroundColor: colors.primary, paddingHorizontal: 12, paddingVertical: 7 },
  addText: { fontSize: 10, fontWeight: '900', color: '#000', letterSpacing: 1 },
  empty: { alignItems: 'center', paddingVertical: 44, gap: 14 },
  emptyText: { fontSize: 14, color: '#555', textAlign: 'center', lineHeight: 22 },
  emptyBtn: { borderWidth: 1, borderColor: colors.primary, paddingHorizontal: 20, paddingVertical: 10 },
  emptyBtnText: { fontSize: 11, fontWeight: '800', color: colors.primary, letterSpacing: 1 },
  row: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#111', borderRadius: 12, padding: 14, gap: 10 },
  addr: { flex: 1, fontSize: 12, color: '#aaa', fontFamily: Platform.OS === 'ios' ? 'Courier' : 'monospace' },
  tag: { fontSize: 9, fontWeight: '700', color: '#555', backgroundColor: '#1a1a1a', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, textTransform: 'uppercase' },
  infoCard: { flex: 1, backgroundColor: '#111', borderRadius: 14, padding: 14, gap: 7 },
  infoTitle: { fontSize: 13, fontWeight: '800', color: '#fff' },
  infoBody: { fontSize: 11, color: '#666', lineHeight: 17 },
  modalBg: { flex: 1, backgroundColor: 'rgba(0,0,0,0.88)', justifyContent: 'flex-end' },
  sheet: { backgroundColor: '#111', borderTopLeftRadius: 26, borderTopRightRadius: 26, padding: 24, paddingBottom: 40, gap: 18 },
  handle: { width: 38, height: 4, backgroundColor: '#2a2a2a', borderRadius: 2, alignSelf: 'center', marginBottom: 4 },
  sheetTitle: { fontSize: 17, fontWeight: '900', color: colors.primary, letterSpacing: 2 },
  typeTabs: { flexDirection: 'row', backgroundColor: '#0d0d0d', borderRadius: 10, padding: 4, gap: 4 },
  typeTab: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 7, paddingVertical: 9, borderRadius: 7 },
  typeTabOn: { backgroundColor: colors.primary },
  typeText: { fontSize: 11, fontWeight: '800', color: '#555' },
  inputWrap: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#0d0d0d', borderRadius: 12, paddingHorizontal: 14, paddingVertical: 13, gap: 10, borderWidth: 1, borderColor: '#1a1a1a' },
  inputFocused: { borderColor: colors.primary },
  input: { flex: 1, fontSize: 13, color: '#fff' },
  confirmBtn: { backgroundColor: colors.primary, height: 52, alignItems: 'center', justifyContent: 'center' },
  confirmText: { fontSize: 13, fontWeight: '900', color: '#000', letterSpacing: 1.5 },
});

// ─────────────────────────────────────────────────────────────────────────────
//  LOGS TAB
// ─────────────────────────────────────────────────────────────────────────────
const MOCK_LOGS = [
  { time: '19:14:02', type: 'ENTRY',    text: 'Buy YES "BTC Above $68,500" — Edge +12.1% — $10 USDC' },
  { time: '19:13:50', type: 'SCAN',     text: 'Scanned 8 markets — 3 signals above threshold' },
  { time: '19:13:41', type: 'TP',       text: 'TAKE_PROFIT "BTC Below $68,200" — PnL +$1.42' },
  { time: '19:13:22', type: 'SL',       text: 'STOP_LOSS "BTC Above $68,700" — PnL −$0.52' },
  { time: '19:13:08', type: 'ENTRY',    text: 'Buy NO "BTC Above $68,700" — Edge +9.3%' },
  { time: '19:12:55', type: 'CANCEL',   text: 'Stale order cancelled on Market_2 after 45s' },
  { time: '19:12:44', type: 'SCAN',     text: 'BTC price updated — $68,412.50' },
  { time: '19:12:30', type: 'ENTRY',    text: 'Buy YES "BTC Above $68,400" — Edge +11.2%' },
  { time: '19:12:15', type: 'ALERT',    text: '🔔 P&L threshold hit — Session +$5.12 USDC' },
  { time: '19:12:00', type: 'SCAN',     text: 'Heartbeat OK — latency 22ms' },
];
const LOG_CLR: Record<string, string> = {
  ENTRY: colors.success, SL: colors.error, TP: colors.primary,
  ALERT: '#FF9800', CANCEL: '#FF6B6B', SCAN: '#444',
};
function LogsTab() {
  return (
    <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ paddingBottom: 16 }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Text style={{ fontSize: 10, fontWeight: '800', color: colors.primary, letterSpacing: 2 }}>SYSTEM_LOGS</Text>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 7 }}>
          <PulseDot /><Text style={{ fontSize: 10, color: colors.primary, fontWeight: '700' }}>LIVE</Text>
        </View>
      </View>
      {MOCK_LOGS.map((l, i) => (
        <Animated.View key={i} entering={FadeInDown.delay(i * 35)} style={log.row}>
          <Text style={log.time}>{l.time}</Text>
          <View style={[log.badge, { backgroundColor: `${LOG_CLR[l.type] || '#333'}18` }]}>
            <Text style={[log.badgeText, { color: LOG_CLR[l.type] || '#555' }]}>{l.type}</Text>
          </View>
          <Text style={log.text} numberOfLines={2}>{l.text}</Text>
        </Animated.View>
      ))}
    </ScrollView>
  );
}
const log = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'flex-start', gap: 8, paddingVertical: 9, borderBottomWidth: 1, borderBottomColor: '#0d0d0d' },
  time: { fontSize: 10, color: '#3a3a3a', fontFamily: Platform.OS === 'ios' ? 'Courier' : 'monospace', width: 56 },
  badge: { paddingHorizontal: 5, paddingVertical: 2, borderRadius: 4, minWidth: 50, alignItems: 'center' },
  badgeText: { fontSize: 8, fontWeight: '900', letterSpacing: 0.4 },
  text: { flex: 1, fontSize: 11, color: '#777', lineHeight: 16 },
});

// ─────────────────────────────────────────────────────────────────────────────
//  ROOT SCREEN
// ─────────────────────────────────────────────────────────────────────────────
export default function Home() {
  const {
    user, isLoading: authLoading, isAuthenticated, isWeb,
    authError, signInWithGoogle, signInWithEmail, signUpWithEmail, signOut,
  } = useAuth();

  const [activeTab, setActiveTab] = useState<TabId>('DASHBOARD');
  const [profileOpen, setProfileOpen] = useState(false);

  const { data: markets = [] } = useQuery<Market[]>({
    queryKey: ['markets'],
    queryFn: async () => (await blink.db.table('markets').list({ orderBy: { expiresAt: 'asc' }, limit: 10 })) as Market[],
    refetchInterval: 9000,
  });

  // Loading splash
  if (authLoading) return <View style={{ flex: 1, backgroundColor: '#000' }} />;

  // Onboarding
  if (!isAuthenticated) {
    return (
      <OnboardingScreen
        isWeb={isWeb}
        authError={authError}
        onGoogle={signInWithGoogle}
        onEmail={signInWithEmail}
        onSignUp={signUpWithEmail}
      />
    );
  }

  // Main app
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: '#000' }} edges={['top']}>
      {/* Header */}
      <View style={app.header}>
        <View>
          <Text style={app.brand}>RECON</Text>
          <Text style={app.brandSub}>HFT TERMINAL v2</Text>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
          <View style={app.statusPill}>
            <PulseDot /><Text style={app.statusText}>BOT ACTIVE</Text>
          </View>
          <TouchableOpacity style={app.avatar} onPress={() => setProfileOpen(true)}>
            <Text style={app.avatarText}>
              {(user?.displayName || user?.email || 'U')[0].toUpperCase()}
            </Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* Tab content */}
      <View style={{ flex: 1, paddingHorizontal: 20, paddingTop: 18 }}>
        {activeTab === 'DASHBOARD' && <DashboardTab markets={markets} />}
        {activeTab === 'STRATEGY'  && <StrategyTab  markets={markets} />}
        {activeTab === 'WALLETS'   && <WalletsTab   user={user} />}
        {activeTab === 'LOGS'      && <LogsTab />}
      </View>

      <BottomNav active={activeTab} onPress={setActiveTab} />

      {/* Profile modal */}
      <Modal visible={profileOpen} animationType="slide" transparent>
        <TouchableOpacity style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.75)' }} onPress={() => setProfileOpen(false)} />
        <Animated.View entering={FadeInDown.springify()} style={app.sheet}>
          <View style={app.sheetHandle} />
          <Text style={app.profileName}>{user?.displayName || 'Trader'}</Text>
          <Text style={app.profileEmail}>{user?.email || ''}</Text>

          <TouchableOpacity style={app.profileRow} onPress={() => { Linking.openURL('https://t.me/PolymarketBTCBot'); setProfileOpen(false); }}>
            <Ionicons name="paper-plane-outline" size={18} color={colors.primary} />
            <Text style={app.profileRowText}>Open Telegram Bot</Text>
          </TouchableOpacity>

          <TouchableOpacity style={[app.profileRow, { borderColor: '#1a1a1a' }]} onPress={() => { signOut(); setProfileOpen(false); }}>
            <Ionicons name="log-out-outline" size={18} color={colors.error} />
            <Text style={[app.profileRowText, { color: colors.error }]}>Sign Out</Text>
          </TouchableOpacity>
        </Animated.View>
      </Modal>
    </SafeAreaView>
  );
}

const app = StyleSheet.create({
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 20, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: '#0d0d0d' },
  brand: { fontSize: 22, fontWeight: '900', color: colors.primary, letterSpacing: 3 },
  brandSub: { fontSize: 9, fontWeight: '700', color: '#333', letterSpacing: 2 },
  statusPill: { flexDirection: 'row', alignItems: 'center', gap: 7, backgroundColor: 'rgba(204,255,0,0.06)', borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6, borderWidth: 1, borderColor: 'rgba(204,255,0,0.12)' },
  statusText: { fontSize: 9, fontWeight: '900', color: colors.primary, letterSpacing: 1 },
  avatar: { width: 36, height: 36, borderRadius: 18, backgroundColor: colors.primary, alignItems: 'center', justifyContent: 'center' },
  avatarText: { fontSize: 15, fontWeight: '900', color: '#000' },
  sheet: { backgroundColor: '#111', borderTopLeftRadius: 26, borderTopRightRadius: 26, padding: 28, paddingBottom: 44, gap: 14 },
  sheetHandle: { width: 38, height: 4, backgroundColor: '#2a2a2a', borderRadius: 2, alignSelf: 'center', marginBottom: 8 },
  profileName: { fontSize: 20, fontWeight: '900', color: '#fff' },
  profileEmail: { fontSize: 13, color: '#666', marginTop: -6 },
  profileRow: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 14, borderWidth: 1, borderColor: '#1a1a1a', borderRadius: 12, paddingHorizontal: 16 },
  profileRowText: { fontSize: 14, fontWeight: '700', color: '#fff' },
});
