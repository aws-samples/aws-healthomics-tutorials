// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.common

import com.amazon.vincent.job.logger.LoggerTrait
import com.amazon.vincent.job.models.ReferenceStoreItem
import htsjdk.samtools.reference.FastaSequenceIndexCreator
import org.apache.spark.sql.SparkSession
import software.amazon.awssdk.auth.credentials.AwsCredentialsProvider

import java.nio.file.Paths

trait DownloadReferenceTrait {
  def logger: LoggerTrait

  def downloadRefToSparkJobs(
      spark: SparkSession,
      referenceStoreDao: ReferenceStoreDao,
      referenceStoreItem: ReferenceStoreItem,
      credentialsProvider: Option[AwsCredentialsProvider] = None): String = {
    val referenceFasta = "reference.fasta"
    val referenceArn = referenceStoreItem.referenceArn
    val referenceIndex = s"$referenceFasta.fai"
    logger.info(s"Downloading Reference File from $referenceArn")
    referenceStoreDao.downloadReference(referenceStoreItem, referenceFasta, credentialsProvider)
    logger.info(
      s"Finished Downloading Reference File from $referenceArn. Creating Index: $referenceIndex")
    FastaSequenceIndexCreator.create(Paths.get(referenceFasta), true)
    spark.sparkContext.addFile(referenceFasta)
    spark.sparkContext.addFile(referenceIndex)
    referenceFasta
  }
}
