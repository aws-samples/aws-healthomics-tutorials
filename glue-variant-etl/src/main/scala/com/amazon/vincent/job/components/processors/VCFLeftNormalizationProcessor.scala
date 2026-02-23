// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.components.processors

import com.amazon.vincent.job.common.{DownloadReferenceTrait, ReferenceStoreDao}
import com.amazon.vincent.job.logger.LoggerTrait
import com.amazon.vincent.job.models.ImportJobParameters
import com.amazon.vincent.job.models.exceptions.VincentInternalException
import io.projectglow.Glow
import io.projectglow.transformers.normalizevariants.VariantNormalizer
import org.apache.spark.sql.DataFrame

class VCFLeftNormalizationProcessor(
    val referenceStoreDao: ReferenceStoreDao,
    val logger: LoggerTrait)
    extends VincentJobProcessor[ImportJobParameters]
    with DownloadReferenceTrait {

  def runNormalization(
      inputDf: DataFrame,
      vincentJobParameter: ImportJobParameters): DataFrame = {

    val referenceStoreItem = vincentJobParameter.referenceStoreItem.getOrElse(
      throw new VincentInternalException(
        "Unable to run Normalization without referenceStoreItem."))

    val referenceFasta =
      downloadRefToSparkJobs(
        spark = inputDf.sparkSession,
        referenceStoreDao = referenceStoreDao,
        referenceStoreItem = referenceStoreItem,
        credentialsProvider = None)

    Glow
      .transform("normalize_variants", inputDf, Map("reference_genome_path" -> referenceFasta))
      .drop(VariantNormalizer.normalizationStatusFieldName)
  }

  override def process(
      inputDf: DataFrame,
      vincentJobParameters: ImportJobParameters): DataFrame = {
    if (vincentJobParameters.runLeftNormalization) {
      runNormalization(inputDf, vincentJobParameters)
    } else {
      inputDf
    }
  }
}
