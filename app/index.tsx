import React, { useState, useEffect, useCallback, useRef } from 'react';
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
  FlatList,
  Alert,
  KeyboardAvoidingView,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons, MaterialCommunityIcons } from '@expo/vector-icons';
import Animated, {
  FadeIn,
  FadeInDown,
  FadeInUp,
  SlideInRight,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withSequence,
  withTiming,
  withSpring,
  interpolate,
} from 'react-native-reanimated';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

import { useAuth } from '@/hooks/useAuth';
import { Platform as RNPlatform } from 'react-native';
import { blink } from '@/lib/blink';
import { colors, spacing, typography, borderRadius, shadows } from '@/constants/design';

const { width: W, height: H } = Dimensions.get('window');

// ─────────────────────────────────────────────
//  TYPES
// ─────────────────────────────────────────────
interface Market {
  id: string;
  title: string;
  strikePrice: number;
  currentPrice: number;
  edge: number;
  expiresAt: string;
}

interface Wallet {
  id: string;
  walletAddress: string;
  walletType: 'custodial' | 'browser';
}

// ─────────────────────────────────────────────
//  ANIMATED PULSE DOT
// ─────────────────────────────────────────────
function PulseDot({ color = colors.primary }: { color?: string }) {
  const scale = useSharedValue(1);
  useEffect(() => {
    scale.value = withRepeat(
      withSequence(withTiming(1.6, { duration: 700 }), withTiming(1, { duration: 700 })),
      -1, true
    );
  }, []);
  const style = useAnimatedStyle(() => ({ transform: [{ scale: scale.value }], opacity: interpolate(scale.value, [1, 1.6], [1, 0.3]) }));
  return (
    <View style={{ width: 8, height: 8, alignItems: 'center', justifyContent: 'center' }}>
      <Animated.View style={[{ width: 8, height: 8, borderRadius: 4, backgroundColor: color }, style]} />
    </View>
  );
}

// ─────────────────────────────────────────────
//  METRIC TILE
// ─────────────────────────────────────────────
function MetricTile({ label, value, sub, accent = false }: { label: string; value: string; sub?: string; accent?: boolean }) {
  return (
    <View style={[tileStyles.tile, accent && tileStyles.accentTile]}>
      {accent && <LinearGradient colors={['rgba(204,255,0,0.18)', 'transparent']} style={StyleSheet.absoluteFillObject} />}
      <Text style={tileStyles.label}>{label}</Text>
      <Text style={[tileStyles.value, accent && { color: colors.primary }]}>{value}</Text>
      {sub ? <Text style={tileStyles.sub}>{sub}</Text> : null}
    </View>
  );
}
const tileStyles = StyleSheet.create({
  tile: { flex: 1, backgroundColor: '#111111', borderRadius: 16, padding: 14, gap: 4 },
  accentTile: { borderWidth: 1, borderColor: 'rgba(204,255,0,0.25)', overflow: 'hidden' },
  label: { fontSize: 9, fontWeight: '700', color: '#666', letterSpacing: 1.5, textTransform: 'uppercase' },
  value: { fontSize: 22, fontWeight: '800', color: '#fff', letterSpacing: -0.5 },
  sub: { fontSize: 10, fontWeight: '600', color: colors.success },
});

// ─────────────────────────────────────────────
//  MARKET ROW
// ─────────────────────────────────────────────
function MarketRow({ market, delay = 0 }: { market: Market; delay?: number }) {
  const isUp = market.title.toLowerCase().includes('above');
  return (
    <Animated.View entering={FadeInDown.delay(delay).springify()}>
      <TouchableOpacity style={rowStyles.row} activeOpacity={0.75}>
        <View style={[rowStyles.direction, { backgroundColor: isUp ? 'rgba(0,255,0,0.1)' : 'rgba(255,0,0,0.1)' }]}>
          <Ionicons name={isUp ? 'arrow-up' : 'arrow-down'} size={14} color={isUp ? colors.success : colors.error} />
        </View>
        <View style={rowStyles.info}>
          <Text style={rowStyles.title} numberOfLines={1}>{market.title}</Text>
          <View style={rowStyles.meta}>
            <Ionicons name="time-outline" size={10} color="#666" />
            <Text style={rowStyles.exp}>EXP {new Date(market.expiresAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</Text>
          </View>
        </View>
        <View style={rowStyles.right}>
          <Text style={rowStyles.price}>${market.currentPrice.toFixed(2)}</Text>
          <View style={rowStyles.edgePill}>
            <Text style={rowStyles.edgeText}>+{market.edge}%</Text>
          </View>
        </View>
      </TouchableOpacity>
    </Animated.View>
  );
}
const rowStyles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#111', borderRadius: 16, padding: 14, gap: 12, borderLeftWidth: 3, borderLeftColor: colors.primary },
  direction: { width: 32, height: 32, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  info: { flex: 1 },
  title: { fontSize: 13, fontWeight: '700', color: '#fff' },
  meta: { flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 3 },
  exp: { fontSize: 10, color: '#666' },
  right: { alignItems: 'flex-end', gap: 4 },
  price: { fontSize: 15, fontWeight: '800', color: '#fff' },
  edgePill: { backgroundColor: 'rgba(204,255,0,0.12)', borderRadius: 6, paddingHorizontal: 6, paddingVertical: 2 },
  edgeText: { fontSize: 9, fontWeight: '900', color: colors.primary },
});

// ─────────────────────────────────────────────
//  WALLET ROW
// ─────────────────────────────────────────────
function WalletRow({ wallet, onRemove }: { wallet: Wallet; onRemove: () => void }) {
  const icon = wallet.walletType === 'custodial' ? 'wallet-outline' : 'globe-outline';
  return (
    <View style={wStyles.row}>
      <Ionicons name={icon as any} size={18} color={colors.primary} />
      <Text style={wStyles.addr} numberOfLines={1}>{wallet.walletAddress}</Text>
      <Text style={wStyles.tag}>{wallet.walletType}</Text>
      <TouchableOpacity onPress={onRemove}>
        <Ionicons name="close-circle" size={18} color="#444" />
      </TouchableOpacity>
    </View>
  );
}
const wStyles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#111', borderRadius: 14, padding: 14, gap: 10 },
  addr: { flex: 1, fontSize: 12, color: '#aaa', fontFamily: Platform.OS === 'ios' ? 'Courier' : 'monospace' },
  tag: { fontSize: 9, fontWeight: '700', color: '#555', backgroundColor: '#1a1a1a', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, textTransform: 'uppercase' },
});

// ─────────────────────────────────────────────
//  BOTTOM NAV
// ─────────────────────────────────────────────
const NAV_TABS = [
  { id: 'DASHBOARD', icon: 'pulse-outline' },
  { id: 'STRATEGY', icon: 'analytics-outline' },
  { id: 'WALLETS', icon: 'wallet-outline' },
  { id: 'LOGS', icon: 'terminal-outline' },
] as const;

type TabId = typeof NAV_TABS[number]['id'];

function BottomNav({ active, onPress }: { active: TabId; onPress: (id: TabId) => void }) {
  return (
    <View style={navStyles.bar}>
      {NAV_TABS.map((tab) => {
        const isActive = active === tab.id;
        return (
          <TouchableOpacity key={tab.id} style={navStyles.item} onPress={() => onPress(tab.id)}>
            <Ionicons name={tab.icon as any} size={22} color={isActive ? colors.primary : '#444'} />
            <Text style={[navStyles.label, isActive && navStyles.labelActive]}>{tab.id}</Text>
            {isActive && <View style={navStyles.dot} />}
          </TouchableOpacity>
        );
      })}
    </View>
  );
}
const navStyles = StyleSheet.create({
  bar: { position: 'absolute', bottom: 0, left: 0, right: 0, flexDirection: 'row', backgroundColor: '#080808', borderTopWidth: 1, borderTopColor: '#1a1a1a', paddingTop: 10, paddingBottom: Platform.OS === 'ios' ? 28 : 12 },
  item: { flex: 1, alignItems: 'center', gap: 3 },
  label: { fontSize: 8, fontWeight: '700', color: '#444', letterSpacing: 1 },
  labelActive: { color: colors.primary },
  dot: { width: 4, height: 4, borderRadius: 2, backgroundColor: colors.primary },
});

// ─────────────────────────────────────────────
//  ONBOARDING SCREEN
// ─────────────────────────────────────────────
function OnboardingScreen({
  onGoogleLogin,
  onEmailLogin,
  onEmailSignup,
  loading,
  authError,
}: {
  onGoogleLogin: () => void;
  onEmailLogin: (e: string, p: string) => void;
  onEmailSignup: (e: string, p: string) => void;
  loading: boolean;
  authError: string | null;
}) {
  const STEPS = [
    { icon: 'flash-circle', title: 'RECON HFT', sub: 'Bayesian edge detection\nfor 5-minute BTC markets.' },
    { icon: 'trending-up', title: 'PRECISION\nEXECUTION', sub: 'Z-Score based limit orders\nautomatically placed at optimal price.' },
    { icon: 'shield-check', title: 'RISK\nCONTROLLED', sub: 'Kelly sizing, delta hedging\nand drawdown protection built-in.' },
  ];
  const [step, setStep] = useState(0);
  const [authMode, setAuthMode] = useState<'options' | 'email'>('options');
  const [emailSignup, setEmailSignup] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [emailFocused, setEmailFocused] = useState(false);
  const [passFocused, setPassFocused] = useState(false);
  const current = STEPS[step];
  const isLast = step === STEPS.length - 1;

  return (
    <View style={ob.container}>
      <LinearGradient colors={['rgba(204,255,0,0.08)', '#000']} style={StyleSheet.absoluteFillObject} />

      {/* Skip */}
      {!isLast && (
        <TouchableOpacity style={ob.skip} onPress={() => setStep(STEPS.length - 1)}>
          <Text style={ob.skipText}>Skip →</Text>
        </TouchableOpacity>
      )}
      {isLast && authMode === 'email' && (
        <TouchableOpacity style={ob.skip} onPress={() => setAuthMode('options')}>
          <Text style={ob.skipText}>← Back</Text>
        </TouchableOpacity>
      )}

      {/* Content */}
      <Animated.View key={`${step}-${authMode}`} entering={FadeInUp.duration(350)} style={ob.content}>
        {authMode === 'options' ? (
          <>
            <MaterialCommunityIcons name={current.icon as any} size={90} color={colors.primary} />
            <Text style={ob.title}>{current.title}</Text>
            <Text style={ob.sub}>{current.sub}</Text>
          </>
        ) : (
          <>
            <MaterialCommunityIcons name="lock-outline" size={60} color={colors.primary} />
            <Text style={ob.title}>{emailSignup ? 'CREATE\nACCOUNT' : 'WELCOME\nBACK'}</Text>
            <Text style={ob.sub}>Enter your credentials to access RECON.</Text>
          </>
        )}
      </Animated.View>

      {/* Step dots (only on step screens) */}
      {authMode === 'options' && (
        <View style={ob.dotsRow}>
          {STEPS.map((_, i) => (
            <View key={i} style={[ob.dot, i === step && ob.dotActive]} />
          ))}
        </View>
      )}

      {/* Error banner */}
      {authError ? (
        <View style={ob.errorBanner}>
          <Ionicons name="alert-circle" size={14} color={colors.error} />
          <Text style={ob.errorText} numberOfLines={2}>{authError.replace('Error: ', '')}</Text>
        </View>
      ) : <View style={{ height: 40 }} />}

      {/* Actions */}
      <Animated.View entering={FadeInDown.delay(300)} style={ob.actions}>
        {!isLast ? (
          <TouchableOpacity style={ob.btn} onPress={() => setStep((s) => s + 1)}>
            <Text style={ob.btnText}>NEXT →</Text>
          </TouchableOpacity>
        ) : authMode === 'options' ? (
          <>
            <TouchableOpacity style={ob.btn} onPress={onGoogleLogin} disabled={loading}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                <Ionicons name="logo-google" size={20} color="#000" />
                <Text style={ob.btnText}>{loading ? 'CONNECTING…' : 'SIGN IN WITH GOOGLE'}</Text>
              </View>
            </TouchableOpacity>
            <TouchableOpacity style={ob.secondaryBtn} onPress={() => setAuthMode('email')}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                <Ionicons name="mail-outline" size={18} color={colors.primary} />
                <Text style={ob.secondaryBtnText}>CONTINUE WITH EMAIL</Text>
              </View>
            </TouchableOpacity>
            <Text style={ob.disclaimer}>
              Trading prediction markets is high risk.\nOnly use capital you can afford to lose.
            </Text>
          </>
        ) : (
          <>
            {/* Email input */}
            <View style={[ob.inputWrap, emailFocused && ob.inputFocused]}>
              <Ionicons name="mail-outline" size={16} color={emailFocused ? colors.primary : '#444'} />
              <TextInput
                style={ob.input}
                placeholder="Email address"
                placeholderTextColor="#444"
                value={email}
                onChangeText={setEmail}
                onFocus={() => setEmailFocused(true)}
                onBlur={() => setEmailFocused(false)}
                keyboardType="email-address"
                autoCapitalize="none"
                autoCorrect={false}
              />
            </View>
            {/* Password input */}
            <View style={[ob.inputWrap, passFocused && ob.inputFocused]}>
              <Ionicons name="lock-closed-outline" size={16} color={passFocused ? colors.primary : '#444'} />
              <TextInput
                style={ob.input}
                placeholder="Password"
                placeholderTextColor="#444"
                value={password}
                onChangeText={setPassword}
                onFocus={() => setPassFocused(true)}
                onBlur={() => setPassFocused(false)}
                secureTextEntry
                autoCapitalize="none"
              />
            </View>
            <TouchableOpacity
              style={[ob.btn, (!email.trim() || !password.trim() || loading) && { opacity: 0.55 }]}
              disabled={!email.trim() || !password.trim() || loading}
              onPress={() => emailSignup ? onEmailSignup(email, password) : onEmailLogin(email, password)}
            >
              <Text style={ob.btnText}>
                {loading ? 'CONNECTING…' : emailSignup ? 'CREATE ACCOUNT' : 'SIGN IN'}
              </Text>
            </TouchableOpacity>
            <TouchableOpacity style={ob.toggleMode} onPress={() => setEmailSignup((v) => !v)}>
              <Text style={ob.toggleText}>
                {emailSignup ? 'Already have an account? Sign in' : "Don't have an account? Sign up"}
              </Text>
            </TouchableOpacity>
          </>
        )}
      </Animated.View>
    </View>
  );
}
const ob = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#000', justifyContent: 'space-between', paddingHorizontal: 28, paddingTop: 80, paddingBottom: 50 },
  skip: { position: 'absolute', top: 56, right: 28, zIndex: 10 },
  skipText: { fontSize: 13, color: '#555', fontWeight: '700' },
  content: { flex: 1, alignItems: 'flex-start', justifyContent: 'center', gap: 20 },
  title: { fontSize: 48, fontWeight: '900', color: colors.primary, lineHeight: 52, letterSpacing: -1 },
  sub: { fontSize: 16, color: '#888', lineHeight: 24, maxWidth: W * 0.75 },
  dotsRow: { flexDirection: 'row', gap: 8, marginBottom: 8 },
  dot: { width: 6, height: 6, borderRadius: 3, backgroundColor: '#222' },
  dotActive: { backgroundColor: colors.primary, width: 20 },
  actions: { gap: 14 },
  btn: { backgroundColor: colors.primary, height: 58, borderRadius: 0, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 24 },
  btnText: { fontSize: 15, fontWeight: '900', color: '#000', letterSpacing: 1.5 },
  secondaryBtn: { height: 52, borderRadius: 0, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: 'rgba(204,255,0,0.4)' },
  secondaryBtnText: { fontSize: 13, fontWeight: '800', color: colors.primary, letterSpacing: 1 },
  disclaimer: { fontSize: 11, color: '#444', textAlign: 'center', lineHeight: 16 },
  errorBanner: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: 'rgba(255,0,0,0.08)', borderRadius: 10, paddingHorizontal: 14, paddingVertical: 10, borderWidth: 1, borderColor: 'rgba(255,0,0,0.25)', marginBottom: 4 },
  errorText: { flex: 1, fontSize: 12, color: colors.error, lineHeight: 16 },
  inputWrap: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#0d0d0d', borderRadius: 0, paddingHorizontal: 16, paddingVertical: 14, gap: 12, borderWidth: 1, borderColor: '#222' },
  inputFocused: { borderColor: colors.primary },
  input: { flex: 1, fontSize: 14, color: '#fff', height: 22 },
  toggleMode: { alignItems: 'center', paddingVertical: 6 },
  toggleText: { fontSize: 12, color: '#555', fontWeight: '600' },
});

// ─────────────────────────────────────────────
//  DASHBOARD TAB
// ─────────────────────────────────────────────
function DashboardTab({ markets }: { markets: Market[] }) {
  return (
    <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ gap: 20, paddingBottom: 16 }}>
      {/* P&L Ring */}
      <Animated.View entering={FadeIn.duration(500)} style={dash.ring}>
        <LinearGradient colors={[colors.primary, '#88FF00']} style={dash.ringGrad}>
          <View style={dash.ringInner}>
            <Text style={dash.ringLabel}>TOTAL P&L</Text>
            <Text style={dash.ringValue}>+$1,420</Text>
            <Text style={dash.ringSub}>+14.2% today</Text>
          </View>
        </LinearGradient>
      </Animated.View>

      {/* Metrics row */}
      <Animated.View entering={FadeInDown.delay(100)} style={{ flexDirection: 'row', gap: 10 }}>
        <MetricTile label="Balance" value="$5,240" sub="+4.2%" accent />
        <MetricTile label="Trades" value="312" sub="+12 /hr" />
        <MetricTile label="Win Rate" value="68%" sub="avg edge 9.4%" />
      </Animated.View>

      {/* Live strategy pill */}
      <Animated.View entering={FadeInDown.delay(150)} style={dash.stratPill}>
        <PulseDot />
        <Text style={dash.stratText}>BAYESIAN_V2_Z_SCORE — RUNNING</Text>
      </Animated.View>

      {/* Horizontal edge cards */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginHorizontal: -20 }} contentContainerStyle={{ paddingHorizontal: 20, gap: 12 }}>
        {markets.map((m) => (
          <View key={m.id} style={dash.edgeCard}>
            <Text style={dash.edgeCardTitle} numberOfLines={1}>{m.title}</Text>
            <View style={dash.edgeBar}>
              <View style={[dash.edgeFill, { width: `${Math.min(100, m.edge * 5)}%` as any }]} />
            </View>
            <Text style={dash.edgeCardVal}>{m.edge}% EDGE</Text>
          </View>
        ))}
      </ScrollView>

      {/* Market list */}
      <View>
        <Text style={dash.sectionLabel}>MARKET_PULSE</Text>
        <View style={{ gap: 10, marginTop: 10 }}>
          {markets.map((m, i) => <MarketRow key={m.id} market={m} delay={i * 60} />)}
        </View>
      </View>
    </ScrollView>
  );
}
const dash = StyleSheet.create({
  ring: { alignItems: 'center' },
  ringGrad: { width: 180, height: 180, borderRadius: 90, padding: 12, alignItems: 'center', justifyContent: 'center' },
  ringInner: { width: 156, height: 156, borderRadius: 78, backgroundColor: '#000', alignItems: 'center', justifyContent: 'center', gap: 2 },
  ringLabel: { fontSize: 9, fontWeight: '700', color: '#555', letterSpacing: 1.5 },
  ringValue: { fontSize: 34, fontWeight: '900', color: colors.primary, letterSpacing: -1 },
  ringSub: { fontSize: 11, fontWeight: '700', color: colors.success },
  stratPill: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: 'rgba(204,255,0,0.07)', borderRadius: 10, paddingHorizontal: 14, paddingVertical: 10, borderWidth: 1, borderColor: 'rgba(204,255,0,0.15)' },
  stratText: { fontSize: 11, fontWeight: '800', color: colors.primary, letterSpacing: 1 },
  edgeCard: { width: 170, backgroundColor: '#111', borderRadius: 16, padding: 14, gap: 10 },
  edgeCardTitle: { fontSize: 12, fontWeight: '700', color: '#fff' },
  edgeBar: { height: 4, backgroundColor: '#222', borderRadius: 2 },
  edgeFill: { height: '100%', backgroundColor: colors.primary, borderRadius: 2 },
  edgeCardVal: { fontSize: 10, fontWeight: '900', color: colors.primary },
  sectionLabel: { fontSize: 10, fontWeight: '800', color: colors.primary, letterSpacing: 2 },
});

// ─────────────────────────────────────────────
//  STRATEGY TAB
// ─────────────────────────────────────────────
function StrategyTab({ markets }: { markets: Market[] }) {
  const PARAMS = [
    { key: 'STRATEGY_ID', val: 'BAYESIAN_V2_Z_SCORE' },
    { key: 'MIN_EDGE', val: '10.0%' },
    { key: 'VOL_PROXY (σ)', val: '100 USD / 5min' },
    { key: 'KELLY_FRACTION', val: '0.25' },
    { key: 'HEDGE_MODE', val: 'DELTA_NEUTRAL' },
    { key: 'ORDER_TYPE', val: 'LIMIT_ONLY' },
    { key: 'MAX_DRAWDOWN', val: '15%' },
    { key: 'TIME_DECAY_MODEL', val: 'SQRT(t/T)' },
  ];
  return (
    <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ gap: 22, paddingBottom: 16 }}>
      <View>
        <Text style={strat.sectionLabel}>EXECUTION_PARAMS</Text>
        <View style={strat.table}>
          {PARAMS.map((p, i) => (
            <View key={p.key} style={[strat.tableRow, i < PARAMS.length - 1 && strat.tableRowBorder]}>
              <Text style={strat.tableKey}>{p.key}</Text>
              <Text style={strat.tableVal}>{p.val}</Text>
            </View>
          ))}
        </View>
      </View>

      <View>
        <Text style={strat.sectionLabel}>SIGNAL_MATRIX</Text>
        <View style={{ gap: 10, marginTop: 10 }}>
          {markets.map((m) => {
            const strong = m.edge >= 10;
            return (
              <Animated.View key={m.id} entering={FadeInDown.springify()} style={strat.signalRow}>
                <View style={[strat.signalDot, { backgroundColor: strong ? colors.primary : '#333' }]} />
                <Text style={strat.signalTitle} numberOfLines={1}>{m.title}</Text>
                <Text style={[strat.signalBadge, { color: strong ? colors.primary : '#555' }]}>
                  {strong ? 'STRONG_BUY' : 'NEUTRAL'}
                </Text>
              </Animated.View>
            );
          })}
        </View>
      </View>

      <View style={strat.infoBox}>
        <Text style={strat.infoTitle}>HOW IT WORKS</Text>
        <Text style={strat.infoText}>
          The bot computes a Z-score:{'\n\n'}
          {'  Z = (BTC_price - Strike) / (σ × √(t/T))'}
          {'\n\n'}
          Where σ = 100 USD volatility proxy and t/T = remaining time fraction. This maps to an expected probability P(Yes). Edge = P(Yes) − Market_Price. Limit orders placed only when edge {'>'} threshold.
        </Text>
      </View>
    </ScrollView>
  );
}
const strat = StyleSheet.create({
  sectionLabel: { fontSize: 10, fontWeight: '800', color: colors.primary, letterSpacing: 2, marginBottom: 10 },
  table: { backgroundColor: '#111', borderRadius: 16, overflow: 'hidden' },
  tableRow: { flexDirection: 'row', justifyContent: 'space-between', padding: 14, alignItems: 'center' },
  tableRowBorder: { borderBottomWidth: 1, borderBottomColor: '#1a1a1a' },
  tableKey: { fontSize: 11, fontWeight: '700', color: '#555', letterSpacing: 0.5 },
  tableVal: { fontSize: 12, fontWeight: '800', color: colors.primary },
  signalRow: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#111', borderRadius: 14, padding: 14, gap: 12 },
  signalDot: { width: 8, height: 8, borderRadius: 4 },
  signalTitle: { flex: 1, fontSize: 13, fontWeight: '700', color: '#fff' },
  signalBadge: { fontSize: 9, fontWeight: '900', letterSpacing: 1 },
  infoBox: { backgroundColor: '#0d0d0d', borderRadius: 16, padding: 20, borderWidth: 1, borderColor: '#1a1a1a' },
  infoTitle: { fontSize: 10, fontWeight: '800', color: '#555', letterSpacing: 2, marginBottom: 12 },
  infoText: { fontSize: 13, color: '#777', lineHeight: 22, fontFamily: Platform.OS === 'ios' ? 'Courier' : 'monospace' },
});

// ─────────────────────────────────────────────
//  WALLETS TAB
// ─────────────────────────────────────────────
function WalletsTab({ user }: { user: any }) {
  const queryClient = useQueryClient();
  const [showModal, setShowModal] = useState(false);
  const [addr, setAddr] = useState('');
  const [type, setType] = useState<'custodial' | 'browser'>('custodial');
  const [inputFocused, setInputFocused] = useState(false);

  const { data: wallets = [], isLoading } = useQuery<Wallet[]>({
    queryKey: ['wallets', user?.id],
    queryFn: async () => {
      if (!user) return [];
      const res = await blink.db.table('user_wallets').list({ where: { user_id: user.id } });
      return res as Wallet[];
    },
    enabled: !!user,
  });

  const addMutation = useMutation({
    mutationFn: async () => {
      if (!user || !addr.trim()) throw new Error('Invalid address');
      return blink.db.table('user_wallets').create({ userId: user.id, walletAddress: addr.trim(), walletType: type });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['wallets', user?.id] });
      setShowModal(false);
      setAddr('');
    },
    onError: (e: any) => Alert.alert('Error', e?.message || 'Failed to link wallet'),
  });

  const removeMutation = useMutation({
    mutationFn: (id: string) => blink.db.table('user_wallets').delete(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['wallets', user?.id] }),
  });

  return (
    <View style={{ flex: 1 }}>
      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ gap: 16, paddingBottom: 16 }}>
        {/* Header */}
        <View style={wall.header}>
          <Text style={wall.sectionLabel}>LINKED_WALLETS</Text>
          <TouchableOpacity style={wall.addBtn} onPress={() => setShowModal(true)}>
            <Ionicons name="add" size={18} color="#000" />
            <Text style={wall.addBtnText}>LINK</Text>
          </TouchableOpacity>
        </View>

        {isLoading ? (
          <Text style={{ color: '#555', fontSize: 13, textAlign: 'center', paddingTop: 40 }}>Loading wallets…</Text>
        ) : wallets.length === 0 ? (
          <Animated.View entering={FadeIn} style={wall.empty}>
            <MaterialCommunityIcons name="wallet-outline" size={48} color="#222" />
            <Text style={wall.emptyText}>No wallets linked yet.{'\n'}Connect a custodial or browser wallet to start trading.</Text>
            <TouchableOpacity style={wall.emptyBtn} onPress={() => setShowModal(true)}>
              <Text style={wall.emptyBtnText}>+ CONNECT WALLET</Text>
            </TouchableOpacity>
          </Animated.View>
        ) : (
          <View style={{ gap: 10 }}>
            {wallets.map((w) => (
              <WalletRow key={w.id} wallet={w} onRemove={() => removeMutation.mutate(w.id)} />
            ))}
          </View>
        )}

        {/* Info blocks */}
        <View style={wall.infoGrid}>
          <View style={wall.infoCard}>
            <MaterialCommunityIcons name="bank-outline" size={24} color={colors.primary} />
            <Text style={wall.infoCardTitle}>Custodial</Text>
            <Text style={wall.infoCardText}>Polymarket-managed wallet. No seed phrase needed.</Text>
          </View>
          <View style={wall.infoCard}>
            <MaterialCommunityIcons name="earth" size={24} color={colors.primary} />
            <Text style={wall.infoCardTitle}>Browser</Text>
            <Text style={wall.infoCardText}>MetaMask / Rabby. You control the keys.</Text>
          </View>
        </View>
      </ScrollView>

      {/* Link Wallet Modal */}
      <Modal visible={showModal} animationType="slide" transparent>
        <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
          <View style={wall.modalBg}>
            <Animated.View entering={FadeInDown.springify()} style={wall.sheet}>
              <View style={wall.sheetHandle} />
              <Text style={wall.sheetTitle}>CONNECT WALLET</Text>

              {/* Type selector */}
              <View style={wall.typeTabs}>
                {(['custodial', 'browser'] as const).map((t) => (
                  <TouchableOpacity key={t} style={[wall.typeTab, type === t && wall.typeTabActive]} onPress={() => setType(t)}>
                    <Ionicons name={t === 'custodial' ? 'wallet-outline' : 'globe-outline'} size={16} color={type === t ? '#000' : '#555'} />
                    <Text style={[wall.typeTabText, type === t && wall.typeTabTextActive]}>{t.toUpperCase()}</Text>
                  </TouchableOpacity>
                ))}
              </View>

              {/* Address input */}
              <View style={[wall.inputWrap, inputFocused && wall.inputFocused]}>
                <Ionicons name="link-outline" size={18} color={inputFocused ? colors.primary : '#444'} />
                <TextInput
                  style={wall.input}
                  placeholder="0x… or Polymarket address"
                  placeholderTextColor="#444"
                  value={addr}
                  onChangeText={setAddr}
                  onFocus={() => setInputFocused(true)}
                  onBlur={() => setInputFocused(false)}
                  autoCapitalize="none"
                  autoCorrect={false}
                />
              </View>

              <TouchableOpacity
                style={[wall.confirmBtn, (!addr.trim() || addMutation.isPending) && { opacity: 0.5 }]}
                onPress={() => addMutation.mutate()}
                disabled={!addr.trim() || addMutation.isPending}
              >
                <Text style={wall.confirmBtnText}>{addMutation.isPending ? 'LINKING…' : 'CONFIRM CONNECT'}</Text>
              </TouchableOpacity>

              <TouchableOpacity style={wall.cancelBtn} onPress={() => { setShowModal(false); setAddr(''); }}>
                <Text style={wall.cancelText}>Cancel</Text>
              </TouchableOpacity>
            </Animated.View>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </View>
  );
}
const wall = StyleSheet.create({
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  sectionLabel: { fontSize: 10, fontWeight: '800', color: colors.primary, letterSpacing: 2 },
  addBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: colors.primary, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 0 },
  addBtnText: { fontSize: 11, fontWeight: '900', color: '#000', letterSpacing: 1 },
  empty: { alignItems: 'center', paddingVertical: 50, gap: 16 },
  emptyText: { fontSize: 14, color: '#555', textAlign: 'center', lineHeight: 22 },
  emptyBtn: { borderWidth: 1, borderColor: colors.primary, paddingHorizontal: 20, paddingVertical: 10 },
  emptyBtnText: { fontSize: 12, fontWeight: '800', color: colors.primary, letterSpacing: 1 },
  infoGrid: { flexDirection: 'row', gap: 12 },
  infoCard: { flex: 1, backgroundColor: '#111', borderRadius: 16, padding: 16, gap: 8 },
  infoCardTitle: { fontSize: 13, fontWeight: '800', color: '#fff' },
  infoCardText: { fontSize: 11, color: '#666', lineHeight: 18 },
  modalBg: { flex: 1, backgroundColor: 'rgba(0,0,0,0.85)', justifyContent: 'flex-end' },
  sheet: { backgroundColor: '#111', borderTopLeftRadius: 28, borderTopRightRadius: 28, padding: 24, paddingBottom: 40, gap: 20 },
  sheetHandle: { width: 40, height: 4, backgroundColor: '#333', borderRadius: 2, alignSelf: 'center', marginBottom: 8 },
  sheetTitle: { fontSize: 18, fontWeight: '900', color: colors.primary, letterSpacing: 2 },
  typeTabs: { flexDirection: 'row', backgroundColor: '#0d0d0d', borderRadius: 12, padding: 4, gap: 4 },
  typeTab: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, paddingVertical: 10, borderRadius: 8 },
  typeTabActive: { backgroundColor: colors.primary },
  typeTabText: { fontSize: 12, fontWeight: '800', color: '#555' },
  typeTabTextActive: { color: '#000' },
  inputWrap: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#0d0d0d', borderRadius: 14, paddingHorizontal: 14, paddingVertical: 14, gap: 10, borderWidth: 1, borderColor: '#1a1a1a' },
  inputFocused: { borderColor: colors.primary },
  input: { flex: 1, fontSize: 13, color: '#fff', height: 24 },
  confirmBtn: { backgroundColor: colors.primary, height: 54, alignItems: 'center', justifyContent: 'center', borderRadius: 0 },
  confirmBtnText: { fontSize: 14, fontWeight: '900', color: '#000', letterSpacing: 1.5 },
  cancelBtn: { alignItems: 'center', paddingVertical: 8 },
  cancelText: { fontSize: 13, color: '#555', fontWeight: '600' },
});

// ─────────────────────────────────────────────
//  LOGS TAB
// ─────────────────────────────────────────────
const MOCK_LOGS = [
  { time: '19:12:07', type: 'ENTRY', text: 'Buy YES on "BTC Above $68,500" — Edge +12.1% — $10 USDC' },
  { time: '19:11:53', type: 'SCAN', text: 'Scanned 8 markets — 3 signals above threshold' },
  { time: '19:11:50', type: 'HEDGE', text: 'Delta hedge triggered on Market_3 — sold NO $5' },
  { time: '19:11:30', type: 'EXIT', text: 'Position closed on "BTC Below $68,200" — PnL +$0.84' },
  { time: '19:11:12', type: 'ENTRY', text: 'Buy NO on "BTC Above $68,700" — Edge +9.3%' },
  { time: '19:10:58', type: 'CANCEL', text: 'Stale order cancelled on Market_2 after 45s' },
  { time: '19:10:44', type: 'SCAN', text: 'BTC price feed updated — $68,412.50' },
  { time: '19:10:30', type: 'ENTRY', text: 'Buy YES on "BTC Above $68,400" — Edge +11.2%' },
  { time: '19:10:15', type: 'HEDGE', text: 'Gamma exposure threshold reached — hedging' },
  { time: '19:10:00', type: 'SCAN', text: 'Bot heartbeat OK — latency 24ms' },
];

const LOG_COLORS: Record<string, string> = {
  ENTRY: colors.success,
  EXIT: '#FF9800',
  HEDGE: colors.primary,
  CANCEL: colors.error,
  SCAN: '#555',
};

function LogsTab() {
  return (
    <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ gap: 2, paddingBottom: 16 }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
        <Text style={{ fontSize: 10, fontWeight: '800', color: colors.primary, letterSpacing: 2 }}>SYSTEM_LOGS</Text>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
          <PulseDot />
          <Text style={{ fontSize: 10, color: colors.primary, fontWeight: '700' }}>LIVE</Text>
        </View>
      </View>
      {MOCK_LOGS.map((log, i) => (
        <Animated.View key={i} entering={FadeInDown.delay(i * 40)} style={logStyles.row}>
          <Text style={logStyles.time}>{log.time}</Text>
          <View style={[logStyles.badge, { backgroundColor: `${LOG_COLORS[log.type]}20` }]}>
            <Text style={[logStyles.badgeText, { color: LOG_COLORS[log.type] || '#555' }]}>{log.type}</Text>
          </View>
          <Text style={logStyles.text} numberOfLines={2}>{log.text}</Text>
        </Animated.View>
      ))}
    </ScrollView>
  );
}
const logStyles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'flex-start', gap: 8, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: '#0d0d0d' },
  time: { fontSize: 10, color: '#444', fontFamily: Platform.OS === 'ios' ? 'Courier' : 'monospace', width: 58 },
  badge: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, minWidth: 52, alignItems: 'center' },
  badgeText: { fontSize: 8, fontWeight: '900', letterSpacing: 0.5 },
  text: { flex: 1, fontSize: 11, color: '#888', lineHeight: 16 },
});

// ─────────────────────────────────────────────
//  ROOT SCREEN
// ─────────────────────────────────────────────
export default function Home() {
  const {
    user,
    isLoading: authLoading,
    isAuthenticated,
    authError,
    signInWithGoogle,
    signInWithEmail,
    signUpWithEmail,
    signOut,
  } = useAuth();
  const [activeTab, setActiveTab] = useState<TabId>('DASHBOARD');
  const [loginLoading, setLoginLoading] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);

  const { data: markets = [] } = useQuery<Market[]>({
    queryKey: ['markets'],
    queryFn: async () => {
      const res = await blink.db.table('markets').list({ orderBy: { expiresAt: 'asc' }, limit: 10 });
      return res as Market[];
    },
    refetchInterval: 8000,
  });

  const handleGoogleLogin = useCallback(async () => {
    setLoginLoading(true);
    try {
      await signInWithGoogle();
    } catch {
      // authError state is set in hook
    } finally {
      setLoginLoading(false);
    }
  }, [signInWithGoogle]);

  const handleEmailLogin = useCallback(async (email: string, password: string) => {
    setLoginLoading(true);
    try {
      await signInWithEmail(email, password);
    } catch {
      // authError state is set in hook
    } finally {
      setLoginLoading(false);
    }
  }, [signInWithEmail]);

  const handleEmailSignup = useCallback(async (email: string, password: string) => {
    setLoginLoading(true);
    try {
      await signUpWithEmail(email, password);
    } catch {
      // authError state is set in hook
    } finally {
      setLoginLoading(false);
    }
  }, [signUpWithEmail]);

  // While checking auth, show blank dark screen (no flash)
  if (authLoading) {
    return <View style={{ flex: 1, backgroundColor: '#000' }} />;
  }

  // Not signed in → onboarding
  if (!isAuthenticated) {
    return (
      <OnboardingScreen
        onGoogleLogin={handleGoogleLogin}
        onEmailLogin={handleEmailLogin}
        onEmailSignup={handleEmailSignup}
        loading={loginLoading}
        authError={authError}
      />
    );
  }

  // Signed in → main app
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: '#000' }} edges={['top']}>
      {/* Header */}
      <View style={appStyles.header}>
        <View>
          <Text style={appStyles.brandName}>RECON</Text>
          <Text style={appStyles.brandSub}>HFT TERMINAL v2</Text>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
          <View style={appStyles.statusPill}>
            <PulseDot />
            <Text style={appStyles.statusText}>BOT ACTIVE</Text>
          </View>
          <TouchableOpacity onPress={() => setProfileOpen(true)} style={appStyles.avatar}>
            <Text style={appStyles.avatarText}>{(user?.displayName || user?.email || 'U')[0].toUpperCase()}</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* Tab Content */}
      <View style={{ flex: 1, paddingHorizontal: 20, paddingTop: 20 }}>
        {activeTab === 'DASHBOARD' && <DashboardTab markets={markets} />}
        {activeTab === 'STRATEGY'  && <StrategyTab  markets={markets} />}
        {activeTab === 'WALLETS'   && <WalletsTab   user={user} />}
        {activeTab === 'LOGS'      && <LogsTab />}
      </View>

      {/* Bottom nav */}
      <BottomNav active={activeTab} onPress={setActiveTab} />

      {/* Profile modal */}
      <Modal visible={profileOpen} animationType="slide" transparent>
        <TouchableOpacity style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.7)' }} onPress={() => setProfileOpen(false)} />
        <Animated.View entering={FadeInDown.springify()} style={appStyles.profileSheet}>
          <View style={appStyles.sheetHandle} />
          <Text style={appStyles.profileName}>{user?.displayName || 'Trader'}</Text>
          <Text style={appStyles.profileEmail}>{user?.email || ''}</Text>
          <TouchableOpacity style={appStyles.profileBtn} onPress={() => { Linking.openURL('https://t.me/PolymarketBTCBot'); setProfileOpen(false); }}>
            <Ionicons name="paper-plane-outline" size={18} color={colors.primary} />
            <Text style={appStyles.profileBtnText}>Open Telegram Bot</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[appStyles.profileBtn, { borderColor: '#333' }]} onPress={() => { signOut(); setProfileOpen(false); }}>
            <Ionicons name="log-out-outline" size={18} color={colors.error} />
            <Text style={[appStyles.profileBtnText, { color: colors.error }]}>Sign Out</Text>
          </TouchableOpacity>
        </Animated.View>
      </Modal>
    </SafeAreaView>
  );
}
const appStyles = StyleSheet.create({
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 20, paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: '#0d0d0d' },
  brandName: { fontSize: 22, fontWeight: '900', color: colors.primary, letterSpacing: 3 },
  brandSub: { fontSize: 9, fontWeight: '700', color: '#444', letterSpacing: 2 },
  statusPill: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: 'rgba(204,255,0,0.07)', borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6, borderWidth: 1, borderColor: 'rgba(204,255,0,0.15)' },
  statusText: { fontSize: 9, fontWeight: '900', color: colors.primary, letterSpacing: 1 },
  avatar: { width: 36, height: 36, borderRadius: 18, backgroundColor: colors.primary, alignItems: 'center', justifyContent: 'center' },
  avatarText: { fontSize: 16, fontWeight: '900', color: '#000' },
  profileSheet: { backgroundColor: '#111', borderTopLeftRadius: 28, borderTopRightRadius: 28, padding: 28, paddingBottom: 40, gap: 16 },
  sheetHandle: { width: 40, height: 4, backgroundColor: '#333', borderRadius: 2, alignSelf: 'center', marginBottom: 8 },
  profileName: { fontSize: 20, fontWeight: '900', color: '#fff' },
  profileEmail: { fontSize: 13, color: '#666', marginTop: -8 },
  profileBtn: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 14, borderWidth: 1, borderColor: '#1a1a1a', borderRadius: 12, paddingHorizontal: 16 },
  profileBtnText: { fontSize: 14, fontWeight: '700', color: '#fff' },
});
