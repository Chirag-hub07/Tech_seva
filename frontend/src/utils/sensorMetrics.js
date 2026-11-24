/**
 * Sensor-to-primary-metric mappings and clinical metadata for the 8 TOLIFE sensor streams.
 *
 * Ensures deterministic clinical metric prioritization, label formatting,
 * and validity flag preservation without silent type conversion or zero-filling.
 */

export const SENSOR_DEFINITIONS = {
  BRI: {
    name: 'Breathing Rate Index',
    shortName: 'Respiratory Rate',
    preferredKeys: ['rf_mean', 'breathing_rate', 'rf_max', 'rf_min'],
    keyLabels: {
      rf_mean: 'Mean respiratory rate',
      rf_max: 'Peak respiratory rate',
      rf_min: 'Minimum respiratory rate',
      rf_std: 'Respiratory rate variation',
      breathing_rate: 'Breathing rate',
    },
    defaultMetricLabel: 'Mean respiratory rate',
  },
  EI: {
    name: 'Environmental Index',
    shortName: 'Environmental Index',
    preferredKeys: ['Mean_Temp', 'temperature', 'Mean_Hum', 'Mean_AQI', 'Max_AQI'],
    keyLabels: {
      Mean_Temp: 'Ambient temperature',
      Max_Temp: 'Max temperature',
      Min_Temp: 'Min temperature',
      Mean_Hum: 'Relative humidity',
      Mean_AQI: 'Air quality index',
      temperature: 'Temperature',
    },
    defaultMetricLabel: 'Ambient temperature',
  },
  MI: {
    name: 'Mobility Index',
    shortName: 'Mobility Index',
    preferredKeys: ['walked_dist', 'activity_score', 'gs_mean', 'smwd_mean'],
    keyLabels: {
      walked_dist: 'Walked distance',
      walked_time: 'Active walk time',
      gs_mean: 'Mean gait speed',
      smwd_mean: 'Mean 6MWD',
      activity_score: 'Activity score',
    },
    defaultMetricLabel: 'Walked distance',
  },
  PEI: {
    name: 'Pulmonary Efficiency Index',
    shortName: 'Pulmonary Efficiency',
    preferredKeys: ['SpO2', 'spo2', 'mean_PEF', 'mean_FEV1', 'HR'],
    keyLabels: {
      SpO2: 'Oxygen saturation',
      spo2: 'Oxygen saturation',
      mean_PEF: 'Peak expiratory flow',
      mean_FEV1: 'Mean FEV1',
      HR: 'Heart rate',
    },
    defaultMetricLabel: 'Oxygen saturation',
  },
  PRVI: {
    name: 'Pulse Rate Variability Index',
    shortName: 'Pulse Rate Variability',
    preferredKeys: ['RMSSD', 'heart_rate_variability', 'nRMSSD', 'mean_HR'],
    keyLabels: {
      RMSSD: 'HRV (RMSSD)',
      nRMSSD: 'Normalized RMSSD',
      mean_HR: 'Mean pulse rate',
      std_RR: 'RR interval std dev',
      heart_rate_variability: 'Heart rate variability',
    },
    defaultMetricLabel: 'HRV (RMSSD)',
  },
  SHRI: {
    name: 'Sleeping Heart Rate Index',
    shortName: 'Sleeping Heart Rate',
    preferredKeys: ['hr_mean', 'sleeping_heart_rate', 'hr_min', 'hr_max'],
    keyLabels: {
      hr_mean: 'Mean sleeping HR',
      hr_min: 'Minimum sleeping HR',
      hr_max: 'Peak sleeping HR',
      hr_std: 'Sleeping HR variation',
      sleeping_heart_rate: 'Sleeping heart rate',
    },
    defaultMetricLabel: 'Mean sleeping HR',
  },
  SII: {
    name: 'Sound Intensity Index',
    shortName: 'Sound Intensity',
    preferredKeys: ['Mean_SI', 'sound_intensity', 'Max_SI', 'Min_SI'],
    keyLabels: {
      Mean_SI: 'Mean sound intensity',
      Max_SI: 'Peak sound intensity',
      Min_SI: 'Minimum sound intensity',
      Std_SI: 'Sound intensity variation',
      sound_intensity: 'Sound intensity',
    },
    defaultMetricLabel: 'Mean sound intensity',
  },
  SQI: {
    name: 'Sleep Quality Index',
    shortName: 'Sleep Quality',
    preferredKeys: ['SE', 'sleep_quality_score', 'sleep_duration', 'WASO'],
    keyLabels: {
      SE: 'Sleep efficiency',
      sleep_duration: 'Sleep duration',
      WASO: 'Wake after sleep onset',
      num_movements: 'Nocturnal movements',
      sleep_quality_score: 'Sleep quality score',
    },
    defaultMetricLabel: 'Sleep efficiency',
  },
}

/**
 * Extract the primary representative metric from a sensor measurement payload.
 *
 * @param {Object} measurement - Raw measurement record
 * @returns {Object} Metric display descriptor
 */
export function extractPrimaryMetric(measurement) {
  if (!measurement) {
    return { key: 'none', label: 'Measurement', value: null, formattedValue: '—', isValid: null }
  }

  const sensorType = measurement.sensor_type || 'Sensor'
  const config = SENSOR_DEFINITIONS[sensorType]
  const metrics = measurement.measurements || measurement.values || {}

  let targetKey = null
  if (config?.preferredKeys) {
    for (const key of config.preferredKeys) {
      if (key in metrics && metrics[key] !== null && metrics[key] !== undefined) {
        targetKey = key
        break
      }
    }
  }

  // Fallback to first available numeric or non-null property if preferred key not found
  if (!targetKey) {
    targetKey = Object.keys(metrics).find((k) => typeof metrics[k] === 'number') || Object.keys(metrics)[0]
  }

  const rawValue = targetKey ? metrics[targetKey] : measurement.value
  const label = config?.keyLabels?.[targetKey] || (targetKey ? targetKey.replaceAll('_', ' ') : (config?.defaultMetricLabel || 'Measurement'))

  let formattedValue = '—'
  if (rawValue !== null && rawValue !== undefined) {
    if (typeof rawValue === 'number') {
      formattedValue = Number.isInteger(rawValue) ? String(rawValue) : rawValue.toFixed(1)
    } else {
      formattedValue = String(rawValue)
    }
  }

  return {
    key: targetKey || 'metric',
    label,
    value: rawValue ?? null,
    formattedValue,
    isValid: measurement.is_valid ?? null,
    sensorType,
  }
}

/**
 * Determine the primary numeric key for time series plotting.
 */
export function getChartNumericKey(data, sensorType) {
  if (!data?.length) return null

  const config = SENSOR_DEFINITIONS[sensorType]
  if (config?.preferredKeys) {
    for (const item of data) {
      const metrics = item.measurements || item.values || {}
      for (const key of config.preferredKeys) {
        if (typeof metrics[key] === 'number') {
          return key
        }
      }
    }
  }

  // Fallback: search for any numeric key in data items
  for (const item of data) {
    const metrics = item.measurements || item.values || {}
    const found = Object.keys(metrics).find((k) => typeof metrics[k] === 'number')
    if (found) return found
  }

  return null
}
