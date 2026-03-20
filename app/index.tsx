import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, Linking, Platform, Modal, TextInput, FlatList, KeyboardAvoidingView } from 'react-native';
import { Card, Button, Container, Avatar } from '@/components/ui';
import { colors, spacing, typography, borderRadius, shadows } from '@/constants/design';
import { Ionicons } from '@expo/vector-icons';
import { useBlinkAuth, useAgent } from '@blinkdotnew/react-native';
import { blink } from '@/lib/blink';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import Animated, { FadeIn, FadeInDown, SlideInRight, Layout } from 'react-native-reanimated';

export default function Home() {
  const { user, isAuthenticated, isLoading: authLoading } = useBlinkAuth();
  const queryClient = useQueryClient();
  const [isWalletModalVisible, setIsWalletModalVisible] = useState(false);
  const [walletAddress, setWalletAddress] = useState('');
  const [walletType, setWalletType] = useState<'custodial' | 'browser'>('custodial');
  const [isChatOpen, setIsChatOpen] = useState(false);

  // Agent for chat interaction
  const { messages, input, setInput, sendMessage, status, error: agentError } = useAgent({
    agentId: 'polymarket-btc-agent',
    initialMessage: 'Hi! I am your Polymarket BTC Trading Assistant. How can I help you today?',
  });

  // Fetch linked wallets
  const { data: wallets = [], isLoading: walletsLoading } = useQuery({
    queryKey: ['wallets', user?.id],
    queryFn: async () => {
      if (!user) return [];
      return await blink.db.table('user_wallets').list({
        where: { user_id: user.id }
      });
    },
    enabled: isAuthenticated && !!user,
  });

  // Fetch markets
  const { data: markets = [], isLoading: marketsLoading } = useQuery({
    queryKey: ['markets'],
    queryFn: async () => {
      return await blink.db.table('markets').list({
        orderBy: { expiresAt: 'asc' },
        limit: 10
      });
    }
  });

  // Link wallet mutation
  const linkWalletMutation = useMutation({
    mutationFn: async () => {
      if (!user || !walletAddress) return;
      return await blink.db.table('user_wallets').create({
        userId: user.id,
        walletAddress,
        walletType,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['wallets', user?.id] });
      setIsWalletModalVisible(false);
      setWalletAddress('');
    },
  });

  const handleLogin = async () => {
    try {
      await blink.auth.signInWithGoogle();
    } catch (error) {
      console.error('Login failed:', error);
    }
  };

  const openTelegram = () => {
    Linking.openURL('https://t.me/PolymarketBTCBot');
  };

  if (authLoading) {
    return (
      <Container style={styles.loadingContainer}>
        <View style={styles.loadingPulse} />
      </Container>
    );
  }

  return (
    <Container safeArea edges={['top', 'bottom']} style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <View>
          <Text style={styles.welcomeText}>
            {isAuthenticated ? `Welcome back, ${user?.displayName || 'Trader'}` : 'Polymarket BTC'}
          </Text>
          <Text style={styles.titleText}>HFT Bot v2</Text>
        </View>
        <View style={styles.headerActions}>
          {!isAuthenticated ? (
            <Button variant="outline" size="sm" onPress={handleLogin} leftIcon={<Ionicons name="logo-google" size={16} />}>
              Sign In
            </Button>
          ) : (
            <TouchableOpacity onPress={() => setIsChatOpen(true)}>
              <Avatar source={{ uri: user?.photoURL }} size="md" />
              <View style={styles.chatBadge} />
            </TouchableOpacity>
          )}
        </View>
      </View>

      <ScrollView 
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        {/* Status Section */}
        <Animated.View entering={FadeInDown.delay(100)}>
          <Card variant="elevated" style={styles.heroCard}>
            <Card.Content>
              <View style={styles.heroHeader}>
                <Text style={styles.heroLabel}>Total P&L (24h)</Text>
                <View style={styles.liveBadge}>
                  <Text style={styles.liveText}>LIVE</Text>
                </View>
              </View>
              <Text style={styles.heroValue}>+$1,420.50</Text>
              <View style={styles.heroStatsRow}>
                <View style={styles.heroStatItem}>
                  <Ionicons name="trending-up" size={16} color={colors.success} />
                  <Text style={styles.heroStatText}>14.2% APY</Text>
                </View>
                <View style={styles.heroStatItem}>
                  <Ionicons name="flash" size={16} color={colors.warning} />
                  <Text style={styles.heroStatText}>312 Trades Today</Text>
                </View>
              </View>
            </Card.Content>
          </Card>
        </Animated.View>

        {/* User Specific Section */}
        {isAuthenticated && (
          <Animated.View entering={FadeInDown.delay(200)}>
            <Text style={styles.sectionTitle}>Your Wallets</Text>
            <View style={styles.walletList}>
              {wallets.map((wallet: any) => (
                <Card key={wallet.id} variant="outline" style={styles.walletCard}>
                  <Card.Content style={styles.walletCardContent}>
                    <Ionicons 
                      name={wallet.walletType === 'custodial' ? 'wallet' : 'browsers'} 
                      size={20} 
                      color={colors.primary} 
                    />
                    <Text style={styles.walletAddress} numberOfLines={1}>
                      {wallet.walletAddress}
                    </Text>
                    <Text style={styles.walletTag}>{wallet.walletType}</Text>
                  </Card.Content>
                </Card>
              ))}
              <TouchableOpacity 
                style={styles.addWalletBtn} 
                onPress={() => setIsWalletModalVisible(true)}
              >
                <Ionicons name="add" size={24} color={colors.textDarkSecondary} />
                <Text style={styles.addWalletText}>Link New Wallet</Text>
              </TouchableOpacity>
            </View>
          </Animated.View>
        )}

        {/* Control Section */}
        <Animated.View entering={FadeInDown.delay(300)}>
          <Text style={styles.sectionTitle}>Intelligence Hub</Text>
          <Card variant="elevated" style={styles.hubCard}>
            <Card.Content>
              <View style={styles.hubRow}>
                <View style={styles.hubInfo}>
                  <View style={styles.hubIconContainer}>
                    <Ionicons name="paper-plane" size={20} color={colors.primary} />
                  </View>
                  <View>
                    <Text style={styles.hubTitle}>Telegram Bot</Text>
                    <Text style={styles.hubSubtitle}>Remote command center</Text>
                  </View>
                </View>
                <Button variant="primary" size="sm" onPress={openTelegram}>
                  Launch
                </Button>
              </View>
              <View style={[styles.hubRow, { marginTop: spacing.md }]}>
                <View style={styles.hubInfo}>
                  <View style={[styles.hubIconContainer, { backgroundColor: 'rgba(236, 72, 153, 0.1)' }]}>
                    <Ionicons name="chatbubbles" size={20} color={colors.accent} />
                  </View>
                  <View>
                    <Text style={styles.hubTitle}>In-App Agent</Text>
                    <Text style={styles.hubSubtitle}>Chat with your bot</Text>
                  </View>
                </View>
                <Button variant="outline" size="sm" onPress={() => setIsChatOpen(true)}>
                  Chat
                </Button>
              </View>
            </Card.Content>
          </Card>
        </Animated.View>

        {/* Market Preview */}
        <Animated.View entering={FadeInDown.delay(400)}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>Market Pulse</Text>
            <TouchableOpacity>
              <Text style={styles.seeAllText}>See All</Text>
            </TouchableOpacity>
          </View>
          {markets.map((market: any, i: number) => (
            <Card key={market.id} variant="outline" style={styles.marketCard}>
              <Card.Content>
                <View style={styles.marketRow}>
                  <View style={styles.marketMain}>
                    <Text style={styles.marketTitle}>{market.title}</Text>
                    <View style={styles.timerRow}>
                      <Ionicons name="time-outline" size={12} color={colors.warning} />
                      <Text style={styles.marketTime}>
                        Expires: {new Date(market.expiresAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </Text>
                    </View>
                  </View>
                  <View style={styles.marketPriceContainer}>
                    <Text style={styles.marketPrice}>${market.currentPrice.toFixed(2)}</Text>
                    <View style={styles.edgeBadge}>
                      <Text style={styles.edgeText}>+{market.edge}% EDGE</Text>
                    </View>
                  </View>
                </View>
              </Card.Content>
            </Card>
          ))}
        </Animated.View>
      </ScrollView>

      {/* Wallet Modal */}
      <Modal visible={isWalletModalVisible} transparent animationType="slide">
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Link Wallet</Text>
              <TouchableOpacity onPress={() => setIsWalletModalVisible(false)}>
                <Ionicons name="close" size={24} color={colors.textDark} />
              </TouchableOpacity>
            </View>
            <View style={styles.walletTypeTabs}>
              <TouchableOpacity 
                style={[styles.walletTypeTab, walletType === 'custodial' && styles.walletTypeTabActive]}
                onPress={() => setWalletType('custodial')}
              >
                <Text style={[styles.walletTypeTabText, walletType === 'custodial' && styles.walletTypeTabTextActive]}>
                  Custodial
                </Text>
              </TouchableOpacity>
              <TouchableOpacity 
                style={[styles.walletTypeTab, walletType === 'browser' && styles.walletTypeTabActive]}
                onPress={() => setWalletType('browser')}
              >
                <Text style={[styles.walletTypeTabText, walletType === 'browser' && styles.walletTypeTabTextActive]}>
                  Browser
                </Text>
              </TouchableOpacity>
            </View>
            <TextInput
              style={styles.modalInput}
              placeholder="Enter Wallet Address"
              placeholderTextColor={colors.textDarkTertiary}
              value={walletAddress}
              onChangeText={setWalletAddress}
            />
            <Button 
              variant="primary" 
              onPress={() => linkWalletMutation.mutate()}
              loading={linkWalletMutation.isPending}
              style={{ marginTop: spacing.md }}
            >
              Connect Wallet
            </Button>
          </View>
        </View>
      </Modal>

      {/* Chat Bot Modal */}
      <Modal visible={isChatOpen} transparent animationType="slide">
        <KeyboardAvoidingView 
          behavior={Platform.OS === 'ios' ? 'padding' : undefined} 
          style={styles.chatOverlay}
        >
          <View style={styles.chatContainer}>
            <View style={styles.chatHeader}>
              <View style={styles.chatHeaderInfo}>
                <View style={styles.chatAvatar}>
                  <Ionicons name="robot" size={20} color={colors.primary} />
                </View>
                <View>
                  <Text style={styles.chatTitle}>Trading Agent</Text>
                  <Text style={styles.chatStatus}>{status === 'typing' ? 'Bot is thinking...' : 'Online'}</Text>
                </View>
              </View>
              <TouchableOpacity onPress={() => setIsChatOpen(false)}>
                <Ionicons name="close" size={24} color={colors.textDark} />
              </TouchableOpacity>
            </View>
            
            <FlatList
              data={messages}
              keyExtractor={(item, index) => index.toString()}
              contentContainerStyle={styles.chatList}
              renderItem={({ item }) => (
                <View style={[
                  styles.messageRow,
                  item.role === 'user' ? styles.userMessageRow : styles.assistantMessageRow
                ]}>
                  <View style={[
                    styles.messageBubble,
                    item.role === 'user' ? styles.userBubble : styles.assistantBubble
                  ]}>
                    <Text style={styles.messageText}>{item.content}</Text>
                  </View>
                </View>
              )}
            />

            <View style={styles.chatInputContainer}>
              <TextInput
                style={styles.chatInput}
                placeholder="Ask me anything about the markets..."
                placeholderTextColor={colors.textDarkTertiary}
                value={input}
                onChangeText={setInput}
                multiline
              />
              <TouchableOpacity 
                style={[styles.sendBtn, !input.trim() && styles.sendBtnDisabled]}
                onPress={sendMessage}
                disabled={!input.trim()}
              >
                <Ionicons name="send" size={20} color={colors.white} />
              </TouchableOpacity>
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </Container>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.backgroundDark,
  },
  loadingContainer: {
    flex: 1,
    backgroundColor: colors.backgroundDark,
    justifyContent: 'center',
    alignItems: 'center',
  },
  loadingPulse: {
    width: 60,
    height: 60,
    borderRadius: 30,
    backgroundColor: colors.primary,
    opacity: 0.5,
  },
  scrollContent: {
    padding: spacing.lg,
    paddingBottom: spacing.xxxxl,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
    marginBottom: spacing.lg,
  },
  headerActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  chatBadge: {
    position: 'absolute',
    top: -2,
    right: -2,
    width: 12,
    height: 12,
    borderRadius: 6,
    backgroundColor: colors.accent,
    borderWidth: 2,
    borderColor: colors.backgroundDark,
  },
  welcomeText: {
    ...typography.caption,
    color: colors.textDarkSecondary,
    fontWeight: '600',
  },
  titleText: {
    ...typography.h2,
    color: colors.textDark,
  },
  heroCard: {
    backgroundColor: colors.backgroundDarkSecondary,
    marginBottom: spacing.xl,
    padding: spacing.xs,
    borderRadius: borderRadius.xl,
  },
  heroHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.xs,
  },
  heroLabel: {
    ...typography.tiny,
    color: colors.textDarkTertiary,
    textTransform: 'uppercase',
    letterSpacing: 1,
  },
  liveBadge: {
    backgroundColor: 'rgba(239, 68, 68, 0.1)',
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 4,
    borderWidth: 1,
    borderColor: colors.error,
  },
  liveText: {
    color: colors.error,
    fontSize: 10,
    fontWeight: '800',
  },
  heroValue: {
    ...typography.display,
    color: colors.success,
    fontSize: 42,
    marginVertical: spacing.xs,
  },
  heroStatsRow: {
    flexDirection: 'row',
    gap: spacing.md,
  },
  heroStatItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  heroStatText: {
    ...typography.tiny,
    color: colors.textDark,
    fontWeight: '600',
  },
  sectionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.md,
  },
  sectionTitle: {
    ...typography.h4,
    color: colors.textDark,
    marginBottom: spacing.md,
  },
  seeAllText: {
    ...typography.tiny,
    color: colors.primary,
    fontWeight: '700',
  },
  walletList: {
    gap: spacing.sm,
    marginBottom: spacing.xl,
  },
  walletCard: {
    backgroundColor: colors.backgroundDarkSecondary,
    borderColor: colors.borderDarkMode,
    borderStyle: 'dashed',
  },
  walletCardContent: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  walletAddress: {
    flex: 1,
    ...typography.caption,
    color: colors.textDark,
    fontFamily: Platform.OS === 'ios' ? 'Courier' : 'monospace',
  },
  walletTag: {
    ...typography.tiny,
    color: colors.textDarkTertiary,
    backgroundColor: colors.backgroundDarkTertiary,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
    textTransform: 'capitalize',
  },
  addWalletBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.xs,
    padding: spacing.md,
    borderRadius: borderRadius.lg,
    borderWidth: 1,
    borderColor: colors.borderDarkMode,
    borderStyle: 'dashed',
  },
  addWalletText: {
    ...typography.captionBold,
    color: colors.textDarkSecondary,
  },
  hubCard: {
    backgroundColor: colors.backgroundDarkSecondary,
    marginBottom: spacing.xl,
    padding: spacing.xs,
  },
  hubRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  hubInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
  },
  hubIconContainer: {
    width: 40,
    height: 40,
    borderRadius: 12,
    backgroundColor: 'rgba(124, 58, 237, 0.1)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  hubTitle: {
    ...typography.bodyBold,
    color: colors.textDark,
  },
  hubSubtitle: {
    ...typography.tiny,
    color: colors.textDarkTertiary,
  },
  marketCard: {
    backgroundColor: colors.backgroundDarkSecondary,
    borderColor: colors.borderDarkMode,
    marginBottom: spacing.sm,
    padding: spacing.xs,
  },
  marketRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  marketMain: {
    flex: 1,
  },
  marketTitle: {
    ...typography.bodyBold,
    color: colors.textDark,
  },
  timerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    marginTop: 2,
  },
  marketTime: {
    ...typography.tiny,
    color: colors.warning,
  },
  marketPriceContainer: {
    alignItems: 'flex-end',
  },
  marketPrice: {
    ...typography.h4,
    color: colors.textDark,
  },
  edgeBadge: {
    backgroundColor: 'rgba(16, 185, 129, 0.1)',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
    marginTop: 4,
  },
  edgeText: {
    color: colors.success,
    fontSize: 9,
    fontWeight: '900',
  },
  // Modal Styles
  modalOverlay: {
    flex: 1,
    backgroundColor: colors.overlayDark,
    justifyContent: 'flex-end',
  },
  modalContent: {
    backgroundColor: colors.backgroundDarkSecondary,
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    padding: spacing.xl,
    minHeight: 400,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.xl,
  },
  modalTitle: {
    ...typography.h3,
    color: colors.textDark,
  },
  walletTypeTabs: {
    flexDirection: 'row',
    backgroundColor: colors.backgroundDarkTertiary,
    borderRadius: 12,
    padding: 4,
    marginBottom: spacing.lg,
  },
  walletTypeTab: {
    flex: 1,
    paddingVertical: 10,
    alignItems: 'center',
    borderRadius: 8,
  },
  walletTypeTabActive: {
    backgroundColor: colors.primary,
  },
  walletTypeTabText: {
    ...typography.captionBold,
    color: colors.textDarkTertiary,
  },
  walletTypeTabTextActive: {
    color: colors.white,
  },
  modalInput: {
    backgroundColor: colors.backgroundDarkTertiary,
    borderRadius: 12,
    padding: spacing.md,
    color: colors.textDark,
    ...typography.body,
    marginBottom: spacing.md,
    borderWidth: 1,
    borderColor: colors.borderDarkMode,
  },
  // Chat Styles
  chatOverlay: {
    flex: 1,
    backgroundColor: colors.overlayDark,
    justifyContent: 'flex-end',
  },
  chatContainer: {
    backgroundColor: colors.backgroundDarkSecondary,
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    height: '80%',
  },
  chatHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: spacing.lg,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderDarkMode,
  },
  chatHeaderInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
  },
  chatAvatar: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.backgroundDarkTertiary,
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: colors.primary,
  },
  chatTitle: {
    ...typography.bodyBold,
    color: colors.textDark,
  },
  chatStatus: {
    ...typography.tiny,
    color: colors.success,
  },
  chatList: {
    padding: spacing.lg,
    gap: spacing.md,
  },
  messageRow: {
    flexDirection: 'row',
    marginBottom: spacing.xs,
  },
  userMessageRow: {
    justifyContent: 'flex-end',
  },
  assistantMessageRow: {
    justifyContent: 'flex-start',
  },
  messageBubble: {
    maxWidth: '80%',
    padding: spacing.md,
    borderRadius: 16,
  },
  userBubble: {
    backgroundColor: colors.primary,
    borderBottomRightRadius: 4,
  },
  assistantBubble: {
    backgroundColor: colors.backgroundDarkTertiary,
    borderBottomLeftRadius: 4,
  },
  messageText: {
    ...typography.body,
    color: colors.textDark,
  },
  chatInputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: spacing.lg,
    gap: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.borderDarkMode,
    backgroundColor: colors.backgroundDarkSecondary,
  },
  chatInput: {
    flex: 1,
    backgroundColor: colors.backgroundDarkTertiary,
    borderRadius: 20,
    paddingHorizontal: spacing.md,
    paddingVertical: 10,
    maxHeight: 100,
    color: colors.textDark,
    ...typography.body,
  },
  sendBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.primary,
    justifyContent: 'center',
    alignItems: 'center',
  },
  sendBtnDisabled: {
    opacity: 0.5,
  },
});
