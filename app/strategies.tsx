/**
 * Trading Strategies Screen
 * Display and toggle bot strategies
 */
import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Switch,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import { Link } from 'expo-router';
import Animated, { FadeInDown } from 'react-native-reanimated';

import { colors, spacing, borderRadius } from '@/constants/design';

interface Strategy {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  risk: 'Low' | 'Medium' | 'High';
}

export default function StrategiesScreen() {
  const [strategies, setStrategies] = useState<Strategy[]>([
    {
      id: 'arbitrage',
      name: 'Arbitrage',
      description: 'Risk-free arbitrage when YES+NO < target price',
      enabled: true,
      risk: 'Low',
    },
    {
      id: 'oracle',
      name: 'Oracle Snipe',
      description: 'Last-second sniping based on BTC price movement',
      enabled: true,
      risk: 'Medium',
    },
    {
      id: 'momentum',
      name: 'Momentum',
      description: 'Statistical momentum edge detection',
      enabled: true,
      risk: 'Medium',
    },
    {
      id: 'cross',
      name: 'Cross-Market',
      description: 'Correlation arbitrage across markets',
      enabled: false,
      risk: 'High',
    },
    {
      id: 'asymmetric',
      name: 'Asymmetric',
      description: 'Cheap-side sniping strategy',
      enabled: true,
      risk: 'Medium',
    },
  ]);

  const toggleStrategy = (id: string) => {
    setStrategies(prev =>
      prev.map(s => s.id === id ? { ...s, enabled: !s.enabled } : s)
    );
  };

  const getRiskColor = (risk: string) => {
    switch (risk) {
      case 'Low': return colors.success;
      case 'Medium': return colors.warning;
      case 'High': return colors.error;
      default: return colors.textSecondary;
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <LinearGradient
        colors={[colors.background, colors.backgroundSecondary]}
        style={styles.gradient}
      >
        <View style={styles.header}>
          <Link href="/" asChild>
            <TouchableOpacity style={styles.backButton}>
              <Ionicons name="arrow-back" size={24} color={colors.primary} />
            </TouchableOpacity>
          </Link>
          <Text style={styles.title}>Trading Strategies</Text>
          <View style={{ width: 40 }} />
        </View>

        <ScrollView style={styles.scrollView} showsVerticalScrollIndicator={false}>
          <Animated.View entering={FadeInDown.delay(100)} style={styles.warning}>
            <Ionicons name="warning" size={20} color={colors.warning} />
            <Text style={styles.warningText}>
              No strategy is 100% foolproof. Always start in dry-run mode.
            </Text>
          </Animated.View>

          {strategies.map((strategy, index) => (
            <Animated.View
              key={strategy.id}
              entering={FadeInDown.delay(200 + index * 100)}
              style={styles.strategyCard}
            >
              <View style={styles.strategyHeader}>
                <View style={styles.strategyInfo}>
                  <Text style={styles.strategyName}>{strategy.name}</Text>
                  <View style={styles.riskBadge}>
                    <Text style={[styles.riskText, { color: getRiskColor(strategy.risk) }]}>
                      {strategy.risk} Risk
                    </Text>
                  </View>
                </View>
                <Switch
                  value={strategy.enabled}
                  onValueChange={() => toggleStrategy(strategy.id)}
                  trackColor={{ false: colors.surface, true: colors.primary }}
                  thumbColor={strategy.enabled ? colors.background : colors.textSecondary}
                />
              </View>
              <Text style={styles.strategyDescription}>{strategy.description}</Text>
            </Animated.View>
          ))}

          <Animated.View entering={FadeInDown.delay(700)} style={styles.infoCard}>
            <Ionicons name="information-circle" size={24} color={colors.primary} />
            <Text style={styles.infoText}>
              Strategies run in parallel. Use Telegram bot commands to toggle live.
              Monitor performance and adjust thresholds regularly.
            </Text>
          </Animated.View>
        </ScrollView>
      </LinearGradient>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  gradient: {
    flex: 1,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.surface,
  },
  backButton: {
    width: 40,
    height: 40,
    borderRadius: borderRadius.md,
    backgroundColor: colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  title: {
    fontSize: 20,
    fontWeight: '700',
    color: colors.primary,
    textAlign: 'center',
  },
  scrollView: {
    flex: 1,
    padding: spacing.lg,
  },
  warning: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    backgroundColor: 'rgba(255,193,7,0.1)',
    borderRadius: borderRadius.md,
    padding: spacing.md,
    marginBottom: spacing.lg,
    borderWidth: 1,
    borderColor: 'rgba(255,193,7,0.2)',
  },
  warningText: {
    flex: 1,
    fontSize: 14,
    color: colors.warning,
    lineHeight: 20,
  },
  strategyCard: {
    backgroundColor: colors.surface,
    borderRadius: borderRadius.lg,
    padding: spacing.lg,
    marginBottom: spacing.md,
    borderWidth: 1,
    borderColor: colors.surface,
  },
  strategyHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.sm,
  },
  strategyInfo: {
    flex: 1,
  },
  strategyName: {
    fontSize: 18,
    fontWeight: '600',
    color: colors.primary,
    marginBottom: spacing.xs,
  },
  riskBadge: {
    backgroundColor: 'rgba(0,0,0,0.05)',
    borderRadius: borderRadius.sm,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
  },
  riskText: {
    fontSize: 12,
    fontWeight: '500',
  },
  strategyDescription: {
    fontSize: 14,
    color: colors.textSecondary,
    lineHeight: 20,
  },
  infoCard: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.sm,
    backgroundColor: 'rgba(204,255,0,0.1)',
    borderRadius: borderRadius.lg,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: 'rgba(204,255,0,0.2)',
  },
  infoText: {
    flex: 1,
    fontSize: 14,
    color: colors.primary,
    lineHeight: 20,
  },
});