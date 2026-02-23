// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.components

import com.amazon.vincent.job.VincentTestSuite
import org.apache.spark.SparkException
import org.apache.spark.sql.test.SharedSparkSession
import org.apache.spark.sql.{DataFrame, QueryTest}
import org.junit.runner.RunWith
import org.mockito.MockitoSugar.{mock, times, verify, when}
import org.scalatest.BeforeAndAfterEach
import org.scalatestplus.junit.JUnitRunner

@RunWith(classOf[JUnitRunner])
class DataFrameUtilsTest
    extends QueryTest
    with BeforeAndAfterEach
    with VincentTestSuite
    with SharedSparkSession {

  var mockDF: DataFrame = _

  override def beforeEach(): Unit = {
    mockDF = mock[DataFrame]
    super.beforeEach()
  }

  test("Exception gets raised with all retries are exhausted") {
    val sparkExceptionMsg = "Failed"
    val writer = new DataFrameV2Writer(testVincentLogger)
    val exception = new SparkException(sparkExceptionMsg)
    val dfName = "./path"
    when(mockDF.writeTo(dfName)).thenThrow(exception)
    val caught = intercept[SparkException](writer.write(mockDF, dfName, Nil))
    verify(mockDF, times(7)).writeTo(dfName)
    assertResult(caught.getMessage)(sparkExceptionMsg)
  }
}
