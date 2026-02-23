// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.models

import org.junit.runner.RunWith
import org.scalatest.funsuite.AnyFunSuite
import org.scalatestplus.junit.JUnitRunner

@RunWith(classOf[JUnitRunner])
class StoreFormatTest extends AnyFunSuite {

  test("Check that valid store formats are converted") {
    assertResult(StoreFormat.VCF)(StoreFormat.withName("VCF"))
    assertResult(StoreFormat.TSV)(StoreFormat.withName("TSV"))
    assertResult(StoreFormat.GFF)(StoreFormat.withName("GFF"))
  }

  test("Check that IllegalArgumentException for invalid  storetype") {
    val caught = intercept[IllegalArgumentException] {
      StoreFormat.withName("CSV")
    }
    assertResult("Unsupported StoreFormat: CSV")(caught.getMessage)
  }
}
