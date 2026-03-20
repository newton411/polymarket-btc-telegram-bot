import React from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, Linking, Platform } from 'react-native';
import { Card, Button, Container } from '@/components/ui';
import { colors, spacing, typography, borderRadius, shadows } from '@/constants/design';
import { Ionicons } from '@expo/vector-icons';

export default function Home() {
  const openTelegram = () => {
    Linking.openURL('https://t.me/PolymarketBTCBot'); // Replace with actual bot link
  };

  return (
    <Container safeArea edges={['top', 'bottom']} style={styles.container}>
      <ScrollView contentContainerStyle={styles.scrollContent}>
        {/* Header Section */}
        <View style={styles.header}>
          <View>
            <Text style={styles.welcomeText}>Polymarket BTC</Text>
            <Text style={styles.titleText}>HFT Trading Bot</Text>
          </View>
          <View style={styles.statusBadge}>
            <View style={styles.statusDot} />
            <Text style={styles.statusText}>SYSTEM ACTIVE</Text>
          </View>
        </View>

        {/* Hero Card */}
        <Card variant="elevated" style={styles.heroCard}>
          <Card.Content>
            <Text style={styles.heroLabel}>Total P&L (24h)</Text>
            <Text style={styles.heroValue}>+$1,240.50</Text>
            <View style={styles.heroStatsRow}>
              <View style={styles.heroStatItem}>
                <Ionicons name="trending-up" size={16} color={colors.success} />
                <Text style={styles.heroStatText}>12.5% Yield</Text>
              </View>
              <View style={styles.heroStatItem}>
                <Ionicons name="flash" size={16} color={colors.warning} />
                <Text style={styles.heroStatText}>245 Trades</Text>
              </View>
            </View>
          </Card.Content>
        </Card>

        {/* Stats Grid */}
        <View style={styles.grid}>
          <Card variant="outline" style={styles.gridItem}>
            <Card.Content>
              <Text style={styles.gridLabel}>Balance</Text>
              <Text style={styles.gridValue}>5,000 USDC</Text>
            </Card.Content>
          </Card>
          <Card variant="outline" style={styles.gridItem}>
            <Card.Content>
              <Text style={styles.gridLabel}>Net Delta</Text>
              <Text style={styles.gridValue}>0.42 BTC</Text>
            </Card.Content>
          </Card>
        </View>

        {/* Control Section */}
        <Text style={styles.sectionTitle}>Control Panel</Text>
        <Card variant="elevated" style={styles.controlCard}>
          <Card.Content>
            <View style={styles.controlRow}>
              <View style={styles.controlInfo}>
                <Ionicons name="paper-plane" size={24} color={colors.primary} />
                <View style={styles.controlTextContainer}>
                  <Text style={styles.controlTitle}>Telegram Dashboard</Text>
                  <Text style={styles.controlSubtitle}>Live alerts & commands</Text>
                </View>
              </View>
              <Button variant="primary" size="md" onPress={openTelegram}>
                Open Bot
              </Button>
            </View>
          </Card.Content>
        </Card>

        {/* Market Section */}
        <Text style={styles.sectionTitle}>Active Markets</Text>
        {[1, 2, 3].map((i) => (
          <Card key={i} variant="outline" style={styles.marketCard}>
            <Card.Content>
              <View style={styles.marketRow}>
                <View>
                  <Text style={styles.marketTitle}>BTC Above $68,500</Text>
                  <Text style={styles.marketTime}>Expires in 3m 45s</Text>
                </View>
                <View style={styles.marketPriceContainer}>
                  <Text style={styles.marketPrice}>$0.65</Text>
                  <Text style={styles.marketEdge}>+8.4% Edge</Text>
                </View>
              </View>
            </Card.Content>
          </Card>
        ))}
      </ScrollView>
    </Container>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.backgroundDark,
  },
  scrollContent: {
    padding: spacing.lg,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.xl,
  },
  welcomeText: {
    ...typography.caption,
    color: colors.textDarkSecondary,
    textTransform: 'uppercase',
    letterSpacing: 1,
  },
  titleText: {
    ...typography.h1,
    color: colors.textDark,
  },
  statusBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(16, 185, 129, 0.1)',
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
    borderRadius: borderRadius.full,
    borderWidth: 1,
    borderColor: colors.success,
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.success,
    marginRight: spacing.xs,
  },
  statusText: {
    ...typography.tiny,
    color: colors.success,
    fontWeight: '700',
  },
  heroCard: {
    backgroundColor: colors.backgroundDarkSecondary,
    marginBottom: spacing.lg,
    padding: spacing.md,
  },
  heroLabel: {
    ...typography.caption,
    color: colors.textDarkSecondary,
    marginBottom: spacing.xs,
  },
  heroValue: {
    ...typography.display,
    color: colors.success,
    fontSize: 48,
    lineHeight: 56,
  },
  heroStatsRow: {
    flexDirection: 'row',
    marginTop: spacing.sm,
    gap: spacing.md,
  },
  heroStatItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  heroStatText: {
    ...typography.captionBold,
    color: colors.textDark,
  },
  grid: {
    flexDirection: 'row',
    gap: spacing.md,
    marginBottom: spacing.xl,
  },
  gridItem: {
    flex: 1,
    backgroundColor: colors.backgroundDarkSecondary,
    borderColor: colors.borderDarkMode,
  },
  gridLabel: {
    ...typography.tiny,
    color: colors.textDarkSecondary,
    textTransform: 'uppercase',
    marginBottom: 4,
  },
  gridValue: {
    ...typography.h4,
    color: colors.textDark,
  },
  sectionTitle: {
    ...typography.h3,
    color: colors.textDark,
    marginBottom: spacing.md,
  },
  controlCard: {
    backgroundColor: colors.backgroundDarkSecondary,
    marginBottom: spacing.xl,
  },
  controlRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  controlInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
  },
  controlTextContainer: {
    flexShrink: 1,
  },
  controlTitle: {
    ...typography.bodyBold,
    color: colors.textDark,
  },
  controlSubtitle: {
    ...typography.caption,
    color: colors.textDarkSecondary,
  },
  marketCard: {
    backgroundColor: colors.backgroundDarkSecondary,
    borderColor: colors.borderDarkMode,
    marginBottom: spacing.sm,
  },
  marketRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  marketTitle: {
    ...typography.bodyBold,
    color: colors.textDark,
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
  marketEdge: {
    ...typography.tiny,
    color: colors.success,
    fontWeight: '700',
  },
});
