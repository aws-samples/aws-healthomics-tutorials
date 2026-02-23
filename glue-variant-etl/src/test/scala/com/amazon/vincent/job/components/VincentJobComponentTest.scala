// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.components

import com.amazon.vincent.job.VincentTestSuite
import com.amazon.vincent.job.components.processors.ExplodeGenotypeProcessor
import com.amazon.vincent.job.logger.LoggerTrait
import org.apache.spark.sql.SparkSession
import org.junit.Assert.assertEquals
import org.junit.runner.RunWith
import org.mockito.MockitoSugar.mock
import org.scalatest.funsuite.AnyFunSuite
import org.scalatestplus.junit.JUnitRunner

@RunWith(classOf[JUnitRunner])
class VincentJobComponentTest extends AnyFunSuite with VincentTestSuite {

  test("Test VariantJobComponent") {
    val logger = mock[LoggerTrait]
    val mockSpark = mock[SparkSession]
    val writer = new DataFrameV2Writer(logger)
    val loader = new VCFDataFrameLoader()
    val processor = new ExplodeGenotypeProcessor
    val variantJobComponent = VariantJobComponent(
      sparkSession = mockSpark,
      dataFrameWriter = writer,
      dataFrameLoader = loader,
      processors = Seq(processor),
      logger = logger)

    assertEquals(mockSpark, variantJobComponent.sparkSession)
    assertEquals(writer, variantJobComponent.dataFrameWriter)
    assertEquals(loader, variantJobComponent.dataFrameLoader)
    assertEquals(Seq(processor), variantJobComponent.processors)
    assertEquals(logger, variantJobComponent.logger)
  }

  test("Test AnnotationVCFJobComponent") {
    val logger = mock[LoggerTrait]
    val mockSpark = mock[SparkSession]
    val writer = new DataFrameV2Writer(logger)
    val loader = new VCFDataFrameLoader()
    val processor = new ExplodeGenotypeProcessor
    val variantJobComponent = AnnotationVCFJobComponent(
      sparkSession = mockSpark,
      dataFrameWriter = writer,
      dataFrameLoader = loader,
      processors = Seq(processor),
      logger = logger)

    assertEquals(mockSpark, variantJobComponent.sparkSession)
    assertEquals(writer, variantJobComponent.dataFrameWriter)
    assertEquals(loader, variantJobComponent.dataFrameLoader)
    assertEquals(Seq(processor), variantJobComponent.processors)
    assertEquals(logger, variantJobComponent.logger)
  }

}
