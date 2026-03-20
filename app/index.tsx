import React, { useState, useEffect, useRef } from 'react';
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
  StatusBar,
  KeyboardAvoidingView
} from 'react-native';
import { Card, Button, Container, Avatar } from '@/components/ui';
import { colors, spacing, typography, borderRadius, shadows } from '@/constants/design';
import { Ionicons, MaterialCommunityIcons } from '@expo/vector-icons';
import { useBlinkAuth, useAgent } from '@blinkdotnew/react-native';
import { blink } from '@/lib/blink';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import Animated, { 
  FadeIn, 
  FadeInDown, 
  SlideInRight, 
  Layout, 
  useAnimatedStyle, 
  withSpring,
  withRepeat,
  withSequence,
  withTiming,
  useSharedValue
} from 'react-native-reanimated';
import { LinearGradient } from 'expo-linear-gradient';

const { width: SCREEN_WIDTH } = Dimensions.get('window');

// --- COMPONENTS ---

const Header = ({ user, isAuthenticated, onLogin, onOpenChat }: any) => (
  <View style={styles.header}>
    <View>
      <Text style={styles.brandTitle}>POLY_HFT</Text>
      <Text style={styles.brandSubtitle}>v2.0 PRO</Text>
    </View>
    <View style={styles.headerActions}>
      {!isAuthenticated ? (
        <TouchableOpacity style={styles.loginBtn} onPress={onLogin}>
          <Ionicons name="logo-google" size={18} color={colors.primary} />
          <Text style={styles.loginBtnText}>CONNECT</Text>
        </TouchableOpacity>
      ) : (
        <TouchableOpacity style={styles.profileBtn} onPress={onOpenChat}>
          <Avatar source={{ uri: user?.photoURL }} size="md" />
          <View style={styles.onlineIndicator} />
        </TouchableOpacity>
      )}
    </View>
  </View>
);

const MetricCard = ({ label, value, trend, icon }: any) => (
  <View style={styles.metricCard}>
    <LinearGradient
      colors={['rgba(204, 255, 0, 0.1)', 'transparent']}
      style={styles.metricGradient}
    />
    <View style={styles.metricHeader}>
      <Text style={styles.metricLabel}>{label}</Text>
      <MaterialCommunityIcons name={icon} size={16} color={colors.primary} />
    </View>
    <Text style={styles.metricValue}>{value}</Text>
    <View style={styles.trendRow}>
      <Ionicons name={trend > 0 ? "trending-up" : "trending-down"} size={12} color={trend > 0 ? colors.success : colors.error} />
      <Text style={[styles.trendText, { color: trend > 0 ? colors.success : colors.error }]}>
        {trend > 0 ? '+' : ''}{trend}%
      </Text>
    </View>
  </View>
);

const MarketItem = ({ market }: any) => (
  <Animated.View entering={FadeInDown} layout={Layout.springify()}>
    <TouchableOpacity style={styles.marketItem}>
      <View style={styles.marketInfo}>
        <Text style={styles.marketTitle}>{market.title}</Text>
        <View style={styles.marketMeta}>
          <Text style={styles.marketTime}>EXP {new Date(market.expiresAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</Text>
          <View style={styles.dotSeparator} />
          <Text style={styles.marketType}>SCALP</Text>
        </View>
      </View>
      <View style={styles.marketValues}>
        <Text style={styles.marketPrice}>${market.currentPrice.toFixed(2)}</Text>
        <View style={styles.edgeBadge}>
          <Text style={styles.edgeText}>+{market.edge}% EDGE</Text>
        </View>
      </View>
    </TouchableOpacity>
  </Animated.View>
);

// --- MAIN SCREEN ---

export default function Home() {
  const { user, isAuthenticated, isLoading: authLoading } = useBlinkAuth();
  const queryClient = useQueryClient();
  const [onboardingStep, setOnboardingStep] = useState(0);
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [activeTab, setActiveTab] = useState('DASHBOARD');

  // Queries
  const { data: markets = [] } = useQuery({
    queryKey: ['markets'],
    queryFn: async () => await blink.db.table('markets').list({ orderBy: { expiresAt: 'asc' }, limit: 5 }),
    refetchInterval: 5000,
  });

  const { data: wallets = [] } = useQuery({
    queryKey: ['wallets', user?.id],
    queryFn: async () => user ? await blink.db.table('user_wallets').list({ where: { user_id: user.id } }) : [],
    enabled: isAuthenticated && !!user,
  });

  const handleLogin = async () => {
    try {
      await blink.auth.signInWithGoogle();
      setOnboardingStep(1);
    } catch (error) {
      console.error('Login error:', error);
    }
  };

  // --- ONBOARDING VIEW ---
  if (!isAuthenticated && !authLoading) {
    return (
      <Container style={styles.onboardingContainer}>
        <StatusBar barStyle="light-content" />
        <LinearGradient
          colors={[colors.primary, 'transparent']}
          style={styles.onboardingGradient}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 1 }}
        />
        <View style={styles.onboardingContent}>
          <Animated.View entering={FadeInDown.duration(1000)} style={styles.heroSection}>
            <MaterialCommunityIcons name="flash-circle" size={80} color={colors.primary} />
            <Text style={styles.onboardingTitle}>RECODE YOUR{'\n'}TRADING</Text>
            <Text style={styles.onboardingSubtitle}>
              HFT Bayesian Scalping for Polymarket BTC 5-Min Markets. Precision execution.
            </Text>
          </Animated.View>

          <Animated.View entering={FadeInDown.delay(500)} style={styles.onboardingActions}>
            <Button 
              variant="primary" 
              size="lg" 
              onPress={handleLogin}
              leftIcon={<Ionicons name="logo-google" size={20} color={colors.black} />}
              style={styles.onboardingBtn}
            >
              GET STARTED
            </Button>
            <Text style={styles.disclaimerText}>
              By connecting, you agree to our Terms & High-Risk Disclaimers.
            </Text>
          </Animated.View>
        </View>
      </Container>
    );
  }

  // --- MAIN DASHBOARD VIEW ---
  return (
    <Container style={styles.container}>
      <StatusBar barStyle="light-content" />
      <Header user={user} isAuthenticated={isAuthenticated} onOpenChat={() => setIsChatOpen(true)} />
      
      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.scrollBody}>
        {/* TOP STATUS RING */}
        <Animated.View entering={FadeInDown.delay(200)} style={styles.performanceSection}>
          <View style={styles.ringContainer}>
            <LinearGradient
              colors={[colors.primary, '#88FF00']}
              style={styles.mainRing}
            >
              <View style={styles.ringInner}>
                <Text style={styles.ringLabel}>PROFIT</Text>
                <Text style={styles.ringValue}>+$1.2k</Text>
                <Text style={styles.ringSubValue}>+12.4%</Text>
              </View>
            </LinearGradient>
          </View>
          <View style={styles.ringStats}>
            <MetricCard label="BALANCE" value="5,240" trend={4.2} icon="wallet-outline" />
            <MetricCard label="TRADES" value="312" trend={12} icon="flash-outline" />
          </View>
        </Animated.View>

        {/* ACTIVE STRATEGY */}
        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>ACTIVE STRATEGY</Text>
          <View style={styles.liveIndicator}>
            <View style={styles.pulseDot} />
            <Text style={styles.liveLabel}>BAYESIAN_V2</Text>
          </View>
        </View>

        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.horizontalScroll}>
          {markets.map((market: any) => (
            <TouchableOpacity key={market.id} style={styles.strategyCard}>
              <Text style={styles.strategyTitle}>{market.title}</Text>
              <View style={styles.edgeMeter}>
                <View style={[styles.edgeProgress, { width: `${market.edge * 5}%` }]} />
              </View>
              <Text style={styles.edgeLabel}>{market.edge}% EDGE DETECTED</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>

        {/* MARKET FEED */}
        <Text style={[styles.sectionTitle, { marginTop: spacing.xl }]}>MARKET PULSE</Text>
        <View style={styles.marketList}>
          {markets.map((market: any) => (
            <MarketItem key={market.id} market={market} />
          ))}
        </View>
      </ScrollView>

      {/* BOTTOM NAV TAB */}
      <View style={styles.bottomNav}>
        {['DASHBOARD', 'STRATEGY', 'LOGS'].map((tab) => (
          <TouchableOpacity 
            key={tab} 
            onPress={() => setActiveTab(tab)}
            style={styles.navItem}
          >
            <Text style={[
              styles.navText, 
              activeTab === tab && styles.navTextActive
            ]}>
              {tab}
            </Text>
            {activeTab === tab && <View style={styles.navIndicator} />}
          </TouchableOpacity>
        ))}
      </View>

      {/* CHAT AGENT OVERLAY */}
      <Modal visible={isChatOpen} animationType="slide" transparent>
        <View style={styles.modalOverlay}>
          <View style={styles.chatContainer}>
            <View style={styles.chatHeader}>
              <Text style={styles.chatTitle}>BOT_INTELLIGENCE</Text>
              <TouchableOpacity onPress={() => setIsChatOpen(false)}>
                <Ionicons name="close" size={24} color={colors.white} />
              </TouchableOpacity>
            </View>
            <View style={styles.chatPlaceholder}>
              <MaterialCommunityIcons name="robot-outline" size={48} color={colors.primary} />
              <Text style={styles.chatText}>Your HFT Agent is ready to analyze. Ask about volatility or active edges.</Text>
              <Button variant="primary" style={{ width: '100%', marginTop: 20 }}>INITIALIZE CHAT</Button>
            </View>
          </View>
        </View>
      </Modal>
    </Container>
  );
}

// --- STYLES ---

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  onboardingContainer: {
    flex: 1,
    backgroundColor: colors.background,
    justifyContent: 'center',
  },
  onboardingGradient: {
    ...StyleSheet.absoluteFillObject,
    opacity: 0.2,
  },
  onboardingContent: {
    padding: spacing.xxl,
    flex: 1,
    justifyContent: 'space-between',
    paddingTop: 100,
  },
  heroSection: {
    alignItems: 'flex-start',
  },
  onboardingTitle: {
    ...typography.display,
    color: colors.primary,
    fontSize: 56,
    lineHeight: 60,
    marginTop: 20,
    fontFamily: Platform.OS === 'ios' ? 'Avenir-Heavy' : 'sans-serif-condensed',
  },
  onboardingSubtitle: {
    ...typography.body,
    color: colors.textSecondary,
    marginTop: 20,
    maxWidth: '80%',
  },
  onboardingActions: {
    gap: 20,
  },
  onboardingBtn: {
    borderRadius: 0,
    height: 60,
    backgroundColor: colors.primary,
  },
  disclaimerText: {
    ...typography.tiny,
    color: colors.textTertiary,
    textAlign: 'center',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: spacing.lg,
    backgroundColor: 'rgba(0,0,0,0.8)',
  },
  brandTitle: {
    ...typography.h3,
    color: colors.primary,
    letterSpacing: 2,
    fontWeight: '900',
  },
  brandSubtitle: {
    ...typography.tiny,
    color: colors.textTertiary,
    fontWeight: '700',
  },
  headerActions: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  loginBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderWidth: 1,
    borderColor: colors.primary,
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  loginBtnText: {
    ...typography.tiny,
    color: colors.primary,
    fontWeight: '900',
  },
  profileBtn: {
    position: 'relative',
  },
  onlineIndicator: {
    position: 'absolute',
    bottom: 0,
    right: 0,
    width: 12,
    height: 12,
    borderRadius: 6,
    backgroundColor: colors.primary,
    borderWidth: 2,
    borderColor: colors.black,
  },
  scrollBody: {
    padding: spacing.lg,
    paddingBottom: 100,
  },
  performanceSection: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: spacing.xl,
    gap: 20,
  },
  ringContainer: {
    width: 160,
    height: 160,
    justifyContent: 'center',
    alignItems: 'center',
  },
  mainRing: {
    width: 160,
    height: 160,
    borderRadius: 80,
    padding: 10,
    justifyContent: 'center',
    alignItems: 'center',
  },
  ringInner: {
    width: 140,
    height: 140,
    borderRadius: 70,
    backgroundColor: colors.black,
    justifyContent: 'center',
    alignItems: 'center',
  },
  ringLabel: {
    ...typography.tiny,
    color: colors.textTertiary,
    letterSpacing: 1,
  },
  ringValue: {
    ...typography.h1,
    color: colors.primary,
    fontSize: 32,
  },
  ringSubValue: {
    ...typography.captionBold,
    color: colors.success,
  },
  ringStats: {
    flex: 1,
    gap: 12,
  },
  metricCard: {
    backgroundColor: colors.secondary,
    padding: 12,
    borderRadius: 12,
    overflow: 'hidden',
  },
  metricGradient: {
    ...StyleSheet.absoluteFillObject,
  },
  metricHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 4,
  },
  metricLabel: {
    ...typography.tiny,
    color: colors.textTertiary,
  },
  metricValue: {
    ...typography.h4,
    color: colors.white,
  },
  trendRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    marginTop: 4,
  },
  trendText: {
    fontSize: 10,
    fontWeight: '700',
  },
  sectionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.md,
  },
  sectionTitle: {
    ...typography.captionBold,
    color: colors.primary,
    letterSpacing: 2,
  },
  liveIndicator: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(204, 255, 0, 0.1)',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 4,
    gap: 6,
  },
  pulseDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: colors.primary,
  },
  liveLabel: {
    fontSize: 10,
    fontWeight: '900',
    color: colors.primary,
  },
  horizontalScroll: {
    marginHorizontal: -spacing.lg,
    paddingLeft: spacing.lg,
  },
  strategyCard: {
    width: 200,
    backgroundColor: colors.secondary,
    padding: 16,
    borderRadius: 16,
    marginRight: 12,
  },
  strategyTitle: {
    ...typography.captionBold,
    color: colors.white,
    marginBottom: 12,
  },
  edgeMeter: {
    height: 4,
    backgroundColor: colors.backgroundTertiary,
    borderRadius: 2,
    marginBottom: 8,
  },
  edgeProgress: {
    height: '100%',
    backgroundColor: colors.primary,
    borderRadius: 2,
  },
  edgeLabel: {
    fontSize: 9,
    color: colors.primary,
    fontWeight: '800',
  },
  marketList: {
    gap: 12,
  },
  marketItem: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: colors.secondary,
    padding: 16,
    borderRadius: 16,
    borderLeftWidth: 4,
    borderLeftColor: colors.primary,
  },
  marketInfo: {
    flex: 1,
  },
  marketTitle: {
    ...typography.bodyBold,
    color: colors.white,
  },
  marketMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: 4,
  },
  marketTime: {
    ...typography.tiny,
    color: colors.warning,
  },
  dotSeparator: {
    width: 3,
    height: 3,
    borderRadius: 1.5,
    backgroundColor: colors.textTertiary,
  },
  marketType: {
    ...typography.tiny,
    color: colors.textTertiary,
  },
  marketValues: {
    alignItems: 'flex-end',
  },
  marketPrice: {
    ...typography.h4,
    color: colors.white,
  },
  edgeBadge: {
    backgroundColor: 'rgba(204, 255, 0, 0.1)',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
    marginTop: 4,
  },
  edgeText: {
    fontSize: 9,
    color: colors.primary,
    fontWeight: '900',
  },
  bottomNav: {
    flexDirection: 'row',
    backgroundColor: 'rgba(0,0,0,0.95)',
    paddingTop: 12,
    paddingBottom: Platform.OS === 'ios' ? 30 : 12,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    position: 'absolute',
    bottom: 0,
    width: '100%',
  },
  navItem: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  navText: {
    fontSize: 10,
    fontWeight: '700',
    color: colors.textTertiary,
  },
  navTextActive: {
    color: colors.primary,
  },
  navIndicator: {
    width: 4,
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.primary,
    marginTop: 4,
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.85)',
    justifyContent: 'flex-end',
  },
  chatContainer: {
    height: '80%',
    backgroundColor: colors.secondary,
    borderTopLeftRadius: 32,
    borderTopRightRadius: 32,
    padding: 24,
  },
  chatHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 40,
  },
  chatTitle: {
    ...typography.h3,
    color: colors.primary,
    letterSpacing: 2,
  },
  chatPlaceholder: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    gap: 20,
  },
  chatText: {
    ...typography.body,
    color: colors.textSecondary,
    textAlign: 'center',
    paddingHorizontal: 40,
  },
});
